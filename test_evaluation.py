"""Regression checks using synthetic data; these are not accuracy evidence."""

import csv
import math
import tempfile
import unittest
from pathlib import Path

from estimate import Point, load_reference
from evaluation import (
    assess_samples, assessment_summary, read_samples, reference_from_samples,
    write_checks,
)


class ImportTests(unittest.TestCase):
    def test_replicates_average_ratios_without_weighting_by_absorbance(self):
        samples = [Point(2, 2, 6), Point(0, 1, 1), Point(1, 2, 3), Point(1, 4, 10)]
        reference = reference_from_samples(samples)
        self.assertEqual([p.concentration for p in reference], [0, 1, 2])
        self.assertEqual([p.ratio for p in reference], [1, 2, 3])
        # Mean(A578) / mean(A434) would incorrectly yield 13/6.
        self.assertNotAlmostEqual(reference[1].ratio, 13 / 6)

    def test_rejects_ambiguous_or_insufficient_calibration(self):
        for samples in (
            [], [Point(0, 1, 1), Point(1, 1, 2)],
            [Point(0, 1, 1), Point(1, 1, 1), Point(2, 1, 3)],
            [Point(0, 1, 1), Point(1, 1, 3), Point(2, 1, 2)],
            [Point(-1, 1, 1), Point(1, 1, 2), Point(2, 1, 3)],
            [Point(0, 1, 1), Point(math.nan, 1, 2), Point(2, 1, 3)],
        ):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                reference_from_samples(samples)

    def test_summary_csv_accepts_explicit_columns_and_preserves_precision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unknown_filename.csv"
            path.write_text("A578_3,concentration_M,A434_2,note\n1.234567890123,0.4,2,반복 1\n",
                            encoding="utf-8-sig")
            self.assertEqual(read_samples(path), [Point(0.4, 2, 1.234567890123)])

    def test_malformed_csv_cannot_silently_drop_bad_measurements(self):
        header = "concentration_M,A434_2,A578_3\n"
        bad_files = ["", header, "concentration_M,A434_2\n0,2\n",
                     header + "0,2\n", header + "0,2,1,extra\n",
                     header + "nan,2,1\n", header + "-1,2,1\n",
                     header + "0,0,1\n", header + "0,2,inf\n",
                     "concentration_M,A434_2,A578_3,A578_3\n0,2,1,3\n"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.csv"
            for content in bad_files:
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        read_samples(path)

    def test_correct_each_replicate_before_averaging_ratios(self):
        samples = [Point(0, 2.2, 1.2, 0.2), Point(1, 2.5, 2.5, 0.5),
                   Point(1, 4.1, 6.1, 0.1), Point(2, 3.2, 6.2, 0.2)]
        reference = reference_from_samples(samples, correct_baseline=True)
        for point, expected in zip(reference, [0.5, 1.25, 2.0]):
            self.assertAlmostEqual(point.ratio, expected)

    def test_import_requires_baseline_in_correction_mode_only(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "data.csv"
            path.write_text('concentration_M,A434_2,A578_3,A730_1\n0,1,1,\n1,1,2,\n2,1,3\n',
                            encoding="utf-8-sig")
            samples = read_samples(path)
            self.assertEqual(len(reference_from_samples(samples)), 3)
            with self.assertRaises(ValueError):
                reference_from_samples(samples, True)
            path.write_text('concentration_M,A434_2,A578_3,A730_1\n0,1,1,nan\n', encoding="utf-8")
            with self.assertRaises(ValueError):
                read_samples(path)


class EvaluationTests(unittest.TestCase):
    def setUp(self):
        self.reference = [Point(0, 1, 1), Point(1, 1, 2), Point(2, 1, 3)]

    def test_threshold_failures_outside_and_duplicates_are_all_counted(self):
        samples = [Point(0.8, 1, 1.5),  # prediction 0.5, exactly -0.3 M
                   Point(0.81, 1, 1.5),  # -0.31 M
                   Point(0.1, 1, 0.9),  # outside, no extrapolation
                   Point(1, 2, 4),  # same concentration and ratio as training
                   Point(0.8, 3, 4.5)]  # repeats first validation record
        checks = assess_samples(samples, self.reference, self.reference)
        self.assertEqual([p.status for p in checks], [
            "목표 이내", "목표 초과", "기준 범위 밖",
            "중복값 · 독립성 확인 필요", "중복값 · 독립성 확인 필요",
        ])
        self.assertAlmostEqual(checks[0].error, -0.3)
        self.assertTrue(all(p.predicted is None for p in checks[2:]))
        summary = assessment_summary(checks)
        for fragment in ("제공된 5개", "목표 이내 1개", "목표 초과 1개", "범위 밖 1개",
                         "독립성 확인 필요 2개", "계산 가능한 2개", "MAE 0.305 M"):
            self.assertIn(fragment, summary)

    def test_training_and_averaged_training_records_are_not_independent_validation(self):
        samples = [Point(0, 1, 1), Point(1, 2, 3), Point(1, 4, 10), Point(2, 2, 6)]
        reference = reference_from_samples(samples)
        checks = assess_samples(reference, reference, samples)
        self.assertTrue(all(p.status.startswith("중복값") for p in checks))
        built_in = load_reference()
        checks = assess_samples(built_in, built_in, built_in)
        self.assertEqual(len(checks), 8)
        self.assertTrue(all(p.predicted is None for p in checks))
        self.assertNotIn("MAE", assessment_summary(checks))

    def test_no_validation_does_not_imply_target_accuracy(self):
        self.assertIn("미확인", assessment_summary([]))
        checks = assess_samples([Point(0.55, 1, 1.5)], self.reference, self.reference)
        self.assertIn("목표 이내 1개", assessment_summary(checks))
        self.assertIn("오차를 보장하지 않습니다", assessment_summary(checks))

    def test_csv_export_keeps_unassessed_rows_and_signed_errors(self):
        checks = assess_samples([Point(0.55, 1, 1.5), Point(0, 1, 0.9)],
                                self.reference, self.reference)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "results.csv"
            write_checks(path, checks, "테스트 검량선")
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(len(rows), 2)
        self.assertAlmostEqual(float(rows[0]["signed_error_M"]), -0.05)
        self.assertEqual(rows[0]["target_M"], "0.3")
        self.assertEqual(rows[1]["predicted_M"], "")
        self.assertEqual(rows[1]["signed_error_M"], "")
        self.assertEqual(rows[1]["status"], "기준 범위 밖")

    def test_calibration_and_validation_use_same_correction(self):
        standards = [Point(0, 2.1, 1.1, 0.1), Point(1, 2.2, 2.2, 0.2), Point(2, 2.3, 3.3, 0.3)]
        reference = reference_from_samples(standards, True)
        samples = [Point(0.6, 2.8, 2.3, 0.8), Point(1, 2.9, 2.9, 0.9)]
        checks = assess_samples(samples, reference, standards, True)
        self.assertAlmostEqual(checks[0].predicted, 0.5)
        self.assertEqual(checks[0].status, "목표 이내")
        self.assertTrue(checks[1].status.startswith("중복값"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checks.csv"
            write_checks(path, checks, "test", "constant_offset_A730_1")
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["correction_mode"], "constant_offset_A730_1")


if __name__ == "__main__":
    unittest.main()
