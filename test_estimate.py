import math
import tempfile
import unittest
from pathlib import Path

from estimate import (
    Point,
    baseline_correct,
    calibration_curve,
    estimate,
    load_reference,
    ratio_from_absorbances,
    read_absorbances,
    validate_reference,
)


class AbsorbanceTests(unittest.TestCase):
    def test_ratio_order_and_zero_numerator(self):
        self.assertEqual(ratio_from_absorbances(2.0, 1.0), 0.5)
        self.assertEqual(ratio_from_absorbances(2.0, 0.0), 0.0)

    def test_invalid_absorbance(self):
        for a434, a578 in [(0, 1), (-1, 1), (1, -1)]:
            with self.subTest(a434=a434, a578=a578), self.assertRaises(ValueError):
                ratio_from_absorbances(a434, a578)

    def test_vernier_encodings_and_wavelength_tolerance(self):
        content = (
            '"0.40M:파장(nm)","0.40M:흡광도"\r\n'
            '433.5,7.0\r\n434.2003,1.25\r\n'
            '577.6,8.0\r\n578.2998,0.75\r\n'
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spectrum.csv"
            for encoding in ("utf-8", "utf-8-sig", "cp949"):
                with self.subTest(encoding=encoding):
                    path.write_bytes(content.encode(encoding))
                    self.assertEqual(read_absorbances(path), (1.25, 0.75))

    def test_missing_target_is_not_replaced_by_a_nearby_wavelength(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "spectrum.csv"
            for low, high in [(434.202, 578.3), (434.2, 578.298)]:
                with self.subTest(low=low, high=high):
                    path.write_text(
                        f'파장(nm),흡광도\n{low},1.25\n{high},0.75\n',
                        encoding="utf-8",
                    )
                    with self.assertRaises(ValueError):
                        read_absorbances(path)


class CalibrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference = load_reference()

    def test_reference_contains_only_the_eight_third_run_points(self):
        expected_ratios = [
            0.8101861149, 0.8242744391, 0.8307260738, 0.8455300817,
            0.8875633352, 0.9709989235, 1.1333620679, 1.2396654268,
        ]
        self.assertEqual([p.concentration for p in self.reference],
                         [0, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6])
        for point, expected in zip(self.reference, expected_ratios):
            self.assertAlmostEqual(point.ratio, expected, places=5)
            self.assertEqual(estimate(point.ratio, self.reference), point.concentration)

    def test_non_third_run_reference_is_rejected(self):
        from estimate import REFERENCE_FILE
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "reference.csv"
            file.write_text(REFERENCE_FILE.read_text(encoding="utf-8").replace(
                "20261105", "20261029", 1), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_reference(file)

    def test_inverse_interpolation_between_adjacent_ratios(self):
        # The monotone Hermite curve has R(0.5)=1.3125 for these three points.
        reference = [Point(0, 1, 1), Point(1, 1, 2), Point(2, 1, 5)]
        self.assertAlmostEqual(float(calibration_curve(reference)(0.5)), 1.3125)
        self.assertAlmostEqual(estimate(1.3125, reference), 0.5)

    def test_forward_curve_is_monotone_and_matches_inverse(self):
        curve = calibration_curve(self.reference)
        previous = -math.inf
        for index in range(161):
            concentration = index / 100
            ratio = float(curve(concentration))
            self.assertGreater(ratio, previous)
            self.assertAlmostEqual(estimate(ratio, self.reference), concentration, places=10)
            previous = ratio
        self.assertTrue(math.isnan(float(curve(-0.1))))
        self.assertTrue(math.isnan(float(curve(1.7))))

    def test_range_and_scaled_endpoints(self):
        low, high = self.reference[0], self.reference[-1]
        self.assertIsNone(estimate(low.ratio - 1e-8, self.reference))
        self.assertIsNone(estimate(high.ratio + 1e-8, self.reference))
        for point in self.reference:
            for scale in (0.1, 3, 7, 10):
                ratio = ratio_from_absorbances(point.a434 * scale, point.a578 * scale)
                self.assertEqual(estimate(ratio, self.reference), point.concentration)

    def test_nonfinite_and_nonmonotonic_inputs(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.assertRaises(ValueError):
                estimate(value, self.reference)
        with self.assertRaises(ValueError):
            estimate(0.9, [Point(0, 1, 1), Point(1, 1, 0.9)])

    def test_filename_and_header_do_not_change_the_estimate(self):
        with tempfile.TemporaryDirectory() as directory:
            results = []
            for name, label, scale in [("0.00M.csv", "0M", 1), ("unknown.csv", "미지", 2)]:
                path = Path(directory) / name
                path.write_text(
                    f"{label}:파장(nm),{label}:흡광도\n"
                    f"434.2,{2.0 * scale}\n578.3,{1.76 * scale}\n",
                    encoding="utf-8",
                )
                ratio = ratio_from_absorbances(*read_absorbances(path))
                results.append(estimate(ratio, self.reference))
            self.assertEqual(results[0], results[1])
            self.assertGreater(results[0], 0.8)

    def test_leave_one_out_validation_uses_only_retained_neighbors(self):
        results = validate_reference(self.reference)
        expected = [0.467965, 0.560441, 0.764508, 0.992156, 1.162268, 1.464389]
        self.assertEqual((len(results.samples), results.total, results.excluded_endpoints), (6, 8, 2))
        for sample, predicted in zip(results.samples, expected):
            self.assertAlmostEqual(sample.predicted, predicted, places=5)
        self.assertAlmostEqual(results.mae, 0.04216355, places=7)
        self.assertAlmostEqual(results.rmse, 0.04668164, places=7)
        self.assertAlmostEqual(results.max_error, 0.06796493, places=7)
        self.assertEqual([p.actual for p in results.samples], [0.4, 0.6, 0.8, 1.0, 1.2, 1.4])


class BaselineTests(unittest.TestCase):
    def test_constant_offset_is_removed_without_changing_source(self):
        for offset in (-0.25, 0.0, 0.4):
            raw = Point(0.8, 2 + offset, 1.4 + offset, offset)
            corrected = baseline_correct(raw)
            self.assertAlmostEqual(corrected.ratio, 0.7)
            self.assertEqual(corrected.concentration, 0.8)
            self.assertEqual(raw.a730, offset)
            # A second correction needs an actual new baseline measurement.
            with self.assertRaises(ValueError):
                baseline_correct(corrected)

    def test_missing_nonfinite_and_nonphysical_corrected_values_are_rejected(self):
        for point in [Point(0, 2, 1), Point(0, 2, 1, math.nan), Point(0, 2, 1, math.inf),
                      Point(0, 2, 1, 2), Point(0, 2, 1, 1.1)]:
            with self.subTest(point=point), self.assertRaises(ValueError):
                baseline_correct(point)

    def test_csv_baseline_is_optional_only_when_correction_is_off(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown.csv"
            base = '파장(nm),흡광도\n434.2,2\n578.3,1\n'
            path.write_text(base + '730.1001,-0.12\n', encoding="utf-8-sig")
            self.assertEqual(read_absorbances(path, True), (2.0, 1.0, -0.12))
            for extra in ('', '730.0,-0.12\n', '730.1,nan\n', '730.1,0\n730.1,0\n'):
                with self.subTest(extra=extra):
                    path.write_text(base + extra, encoding="utf-8")
                    self.assertEqual(read_absorbances(path), (2.0, 1.0))
                    with self.assertRaises(ValueError):
                        read_absorbances(path, True)

    def test_corrected_third_run_leave_one_out_errors(self):
        raw = load_reference()
        reference = [baseline_correct(point) for point in raw]
        result = validate_reference(reference)
        self.assertAlmostEqual(result.mae, 0.03173384283611814, places=10)
        self.assertAlmostEqual(result.rmse, 0.03869204757330943, places=10)
        self.assertAlmostEqual(result.max_error, 0.06923745941334847, places=10)
        self.assertEqual(len(result.samples), 6)
        self.assertEqual(result.excluded_endpoints, 2)
        self.assertTrue(all(abs(p.error) <= 0.3 for p in result.samples))
        for point, corrected in zip(raw, reference):
            self.assertEqual(estimate(corrected.ratio, reference), point.concentration)

    def test_all_three_scaled_absorbances_preserve_the_estimate(self):
        raw = load_reference()
        reference = [baseline_correct(p) for p in raw]
        for point in raw:
            scaled = Point(point.concentration, point.a434 * 7, point.a578 * 7, point.a730 * 7)
            self.assertEqual(estimate(baseline_correct(scaled).ratio, reference), point.concentration)

    def test_known_cross_run_error_is_not_clipped_to_target(self):
        reference = [baseline_correct(p) for p in load_reference()]
        sample = Point(0, 1.920084262490706, 1.5943531527076669, -0.08160303005360392)
        prediction = estimate(baseline_correct(sample).ratio, reference)
        self.assertAlmostEqual(prediction, 0.5642411119851022, places=10)
        self.assertGreater(abs(prediction - sample.concentration), 0.3)


if __name__ == "__main__":
    unittest.main()
