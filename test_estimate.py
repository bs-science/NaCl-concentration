import math
import tempfile
import unittest
from pathlib import Path

from estimate import (
    Point,
    estimate,
    inverse_candidates,
    load_runs,
    ratio_from_absorbances,
    read_absorbances,
    validate_runs,
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
        cls.runs = load_runs()
        cls.reference = cls.runs[2]

    def test_bundled_runs_match_independently_checked_spectra(self):
        concentrations = [0.0, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6]
        expected_endpoints = [
            (0.86370151, 0.89003226),
            (0.83035583, 1.45226503),
            (0.81018611, 1.23966543),
        ]
        self.assertEqual(len(self.runs), 3)
        for run, (first, last) in zip(self.runs, expected_endpoints):
            with self.subTest(first=first):
                self.assertEqual([p.concentration for p in run], concentrations)
                self.assertAlmostEqual(run[0].ratio, first, places=7)
                self.assertAlmostEqual(run[-1].ratio, last, places=7)
                for point in run:
                    self.assertAlmostEqual(point.ratio, point.a578 / point.a434)

    def test_inverse_interpolation_between_adjacent_ratios(self):
        # Third run: R is halfway from its 1.20 M value to its 1.40 M value.
        left, right = self.reference[5:7]
        midpoint = (left.ratio + right.ratio) / 2
        self.assertAlmostEqual(estimate(midpoint, self.reference), 1.3)

    def test_range_includes_endpoints_and_excludes_extrapolation(self):
        low, high = self.reference[0], self.reference[-1]
        self.assertAlmostEqual(estimate(low.ratio, self.reference), 0.0)
        self.assertAlmostEqual(estimate(high.ratio, self.reference), 1.6)
        self.assertIsNone(estimate(math.nextafter(low.ratio, -math.inf), self.reference))
        self.assertIsNone(estimate(math.nextafter(high.ratio, math.inf), self.reference))

    def test_nonfinite_ratio(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                estimate(value, self.reference)

    def test_all_inverse_candidates_for_the_first_run_zero_standard(self):
        # Exact ratio of the measurements; truncation can move it outside run 1.
        ratio = 1.8193373293737674 / 2.106442219282868
        expected = [[0.0], [0.05383237, 0.59766541, 0.61701927], [0.88646215]]
        for run_number, (run, want) in enumerate(zip(self.runs, expected), 1):
            with self.subTest(run=run_number):
                candidates = sorted(inverse_candidates(ratio, run))
                self.assertEqual(len(candidates), len(want))
                for (low, high), concentration in zip(candidates, want):
                    self.assertAlmostEqual(low, concentration, places=7)
                    self.assertAlmostEqual(high, concentration, places=7)

    def test_shared_vertex_is_counted_once_and_outside_ratios_have_no_candidates(self):
        run = [Point(0.0, 1.0, 1.0), Point(0.4, 1.0, 2.0), Point(0.6, 1.0, 1.0)]
        self.assertEqual(inverse_candidates(2.0, run), [(0.4, 0.4)])
        self.assertEqual(inverse_candidates(2.01, run), [])
        self.assertEqual(inverse_candidates(0.99, run), [])

    def test_scaling_both_absorbances_keeps_an_endpoint_or_turning_point(self):
        for run in self.runs:
            for point in run:
                for scale in (0.1, 3, 7, 10):
                    ratio = ratio_from_absorbances(point.a434 * scale, point.a578 * scale)
                    candidates = inverse_candidates(ratio, run)
                    self.assertTrue(any(lo <= point.concentration <= hi for lo, hi in candidates))

    def test_adjacent_flat_segments_form_one_interval_alongside_isolated_roots(self):
        ratios = [0.0, 2.0, 1.0, 1.0, 1.0, 0.0, 2.0]
        run = [Point(float(i), 1.0, ratio) for i, ratio in enumerate(ratios)]
        self.assertEqual(
            sorted(inverse_candidates(1.0, run)),
            [(0.5, 0.5), (2.0, 4.0), (5.5, 5.5)],
        )

    def test_file_names_and_common_absorbance_scale_do_not_change_candidates(self):
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
                self.assertAlmostEqual(ratio, 0.88)
                results.append([inverse_candidates(ratio, run) for run in self.runs])
        self.assertTrue(all(results[0]))
        self.assertEqual(results[0], results[1])

    def test_validation_coverage_and_mean_absolute_error(self):
        expected = [(6, 6, 0.05964645), (8, 8, 0.42548567), (4, 8, 0.50073708)]
        results = validate_runs(self.runs)
        self.assertEqual(len(results), len(expected))
        for (name, count, total, mae), (want_count, want_total, want_mae) in zip(
            results, expected
        ):
            with self.subTest(group=name):
                self.assertEqual((count, total), (want_count, want_total))
                self.assertAlmostEqual(mae, want_mae, places=7)


if __name__ == "__main__":
    unittest.main()
