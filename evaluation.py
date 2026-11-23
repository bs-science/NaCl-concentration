"""Calibration imports and held-out validation for concentration estimates."""

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from estimate import Point, baseline_correct, calibration_curve, estimate


TARGET_ERROR = 0.3


def read_samples(path: Path | str) -> list[Point]:
    """Read explicit concentrations and absorbances from a summary CSV."""
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"concentration_M", "A434_2", "A578_3"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("concentration_M, A434_2, A578_3 열이 필요합니다.")
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError("중복된 열 이름이 있습니다.")
        samples = []
        for number, row in enumerate(reader, 2):
            try:
                if None in row:
                    raise ValueError("열 이름보다 많은 값이 있습니다. 쉼표 구분을 확인하세요.")
                point = Point(float(row["concentration_M"]),
                              float(row["A434_2"]), float(row["A578_3"]),
                              float(row["A730_1"]) if (row.get("A730_1") or "").strip() else None)
                if not math.isfinite(point.concentration) or point.concentration < 0:
                    raise ValueError("농도는 0 이상의 유한한 값이어야 합니다.")
                if point.a730 is not None and not math.isfinite(point.a730):
                    raise ValueError("730.1 nm 흡광도는 유한한 값이어야 합니다.")
                point.ratio
            except (ValueError, TypeError) as exc:
                raise ValueError(f"{number}행을 확인하세요. {exc}") from exc
            samples.append(point)
    if not samples:
        raise ValueError("측정 자료가 비어 있습니다.")
    return samples


def reference_from_samples(samples: list[Point], correct_baseline: bool = False) -> list[Point]:
    groups = {}
    for point in samples:
        if correct_baseline:
            point = baseline_correct(point)
        if not math.isfinite(point.concentration) or point.concentration < 0:
            raise ValueError("농도는 0 이상의 유한한 값이어야 합니다.")
        groups.setdefault(point.concentration, []).append(point.ratio)
    if len(groups) < 3:
        raise ValueError("서로 다른 농도 조건이 세 개 이상 필요합니다.")
    # Average the ratios of replicate standards at the same concentration.
    reference = [Point(c, 1.0, mean(groups[c])) for c in sorted(groups)]
    calibration_curve(reference)
    return reference


@dataclass(frozen=True)
class Check:
    actual: float
    ratio: float
    predicted: float | None
    status: str

    @property
    def error(self) -> float | None:
        return None if self.predicted is None else self.predicted - self.actual


def assess_samples(samples: list[Point], reference: list[Point],
                   calibration_samples: list[Point], correct_baseline: bool = False) -> list[Check]:
    """Keep out-of-range and overlapping records visible in target assessment."""
    if correct_baseline:
        samples = [baseline_correct(p) for p in samples]
        calibration_samples = [baseline_correct(p) for p in calibration_samples]
    checks = []
    seen = []
    for point in samples:
        if any(point.concentration == old.concentration
               and math.isclose(point.ratio, old.ratio, rel_tol=0, abs_tol=1e-12)
               for old in calibration_samples + reference + seen):
            checks.append(Check(point.concentration, point.ratio, None, "중복값 · 독립성 확인 필요"))
        else:
            prediction = estimate(point.ratio, reference)
            if prediction is None:
                status = "기준 범위 밖"
            elif abs(prediction - point.concentration) <= TARGET_ERROR + 1e-12:
                status = "목표 이내"
            else:
                status = "목표 초과"
            checks.append(Check(point.concentration, point.ratio, prediction, status))
        seen.append(point)
    return checks


def assessment_summary(checks: list[Check]) -> str:
    if not checks:
        return "별도 검증자료 미등록 · 미지 시료의 ±0.30 M 달성 여부 미확인"
    errors = [check.error for check in checks if check.error is not None]
    passed = sum(check.status == "목표 이내" for check in checks)
    failed = sum(check.status == "목표 초과" for check in checks)
    outside = sum(check.status == "기준 범위 밖" for check in checks)
    overlap = sum(check.status.startswith("중복값") for check in checks)
    message = (f"제공된 {len(checks)}개 중 목표 이내 {passed}개 · 목표 초과 {failed}개 · "
               f"범위 밖 {outside}개 · 독립성 확인 필요 {overlap}개")
    if errors:
        message += (f"\n계산 가능한 {len(errors)}개에서 MAE {mean(abs(e) for e in errors):.3f} M · "
                    f"RMSE {math.sqrt(mean(e * e for e in errors)):.3f} M · "
                    f"최대절대오차 {max(abs(e) for e in errors):.3f} M")
    return message + "\n이 판정은 제공된 시료에 한정되며 미지 시료의 오차를 보장하지 않습니다."


def write_checks(path: Path | str, checks: list[Check], calibration_name: str,
                 correction_mode: str = "none") -> None:
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["calibration", "actual_M", "ratio", "predicted_M",
                         "signed_error_M", "target_M", "status", "correction_mode"])
        for check in checks:
            writer.writerow([calibration_name, check.actual, check.ratio,
                             "" if check.predicted is None else check.predicted,
                             "" if check.error is None else check.error, TARGET_ERROR, check.status,
                             correction_mode])
