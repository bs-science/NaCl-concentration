"""Estimate added NaCl concentration from the third Tris–mCP experiment."""

from __future__ import annotations

import csv
import io
import math
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from statistics import mean

from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq


REFERENCE_FILE = Path(__file__).with_name("reference.csv")
RUN_DATE = "20261105"
CONCENTRATIONS = (0.0, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6)
WAVELENGTHS = (434.2, 578.3)
BASELINE_WAVELENGTH = 730.1


def ratio_from_absorbances(a434: float, a578: float) -> float:
    if not math.isfinite(a434) or a434 <= 0:
        raise ValueError("434.2 nm 흡광도에는 0보다 큰 유한한 값을 입력하세요.")
    if not math.isfinite(a578) or a578 < 0:
        raise ValueError("578.3 nm 흡광도에는 0 이상의 유한한 값을 입력하세요.")
    ratio = a578 / a434
    if not math.isfinite(ratio):
        raise ValueError("두 흡광도의 비율이 계산 범위를 벗어났습니다.")
    return ratio


@dataclass(frozen=True)
class Point:
    concentration: float
    a434: float
    a578: float
    a730: float | None = None

    @property
    def ratio(self) -> float:
        return ratio_from_absorbances(self.a434, self.a578)


def baseline_correct(point: Point) -> Point:
    """Remove a measured constant optical offset; this is not a matrix blank."""
    if point.a730 is None or not math.isfinite(point.a730):
        raise ValueError("바탕선 보정에는 유한한 730.1 nm 흡광도가 필요합니다.")
    corrected = Point(point.concentration, point.a434 - point.a730,
                      point.a578 - point.a730)
    try:
        corrected.ratio
    except ValueError as exc:
        raise ValueError("바탕선 보정 후 흡광도가 유효하지 않습니다. 측정값을 확인하세요.") from exc
    return corrected


def load_reference(path: Path | str = REFERENCE_FILE) -> list[Point]:
    points = []
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"run_date", "concentration_M", "A434_2", "A578_3"}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("기준 파일의 날짜·농도·두 파장 흡광도 열을 확인하세요.")
        for row in reader:
            if row["run_date"] != RUN_DATE:
                raise ValueError("기준 파일에는 2026-11-05의 3차 실험 자료만 사용할 수 있습니다.")
            points.append(Point(float(row["concentration_M"]),
                                float(row["A434_2"]), float(row["A578_3"]),
                                float(row["A730_1"]) if row.get("A730_1") else None))
    points.sort(key=lambda point: point.concentration)
    if tuple(point.concentration for point in points) != CONCENTRATIONS:
        raise ValueError("3차 기준 파일의 농도 조건 8개를 확인하세요.")
    _validate_reference(points)
    return points


def _validate_reference(reference: list[Point]) -> list[float]:
    if len(reference) < 2:
        raise ValueError("기준점이 두 개 이상 필요합니다.")
    if any(not math.isfinite(p.concentration) for p in reference):
        raise ValueError("기준 농도가 유한한 값이어야 합니다.")
    if any(a.concentration >= b.concentration for a, b in zip(reference, reference[1:])):
        raise ValueError("기준 농도가 순서대로 증가해야 합니다.")
    ratios = [point.ratio for point in reference]
    if any(a >= b for a, b in zip(ratios, ratios[1:])):
        raise ValueError("기준 흡광도비가 순서대로 증가해야 합니다.")
    return ratios


def calibration_curve(reference: list[Point]) -> PchipInterpolator:
    """Interpolate R as a monotone function of concentration, without extrapolation."""
    ratios = _validate_reference(reference)
    return PchipInterpolator([p.concentration for p in reference], ratios, extrapolate=False)


def estimate(ratio: float, reference: list[Point]) -> float | None:
    """Invert the forward PCHIP calibration within the measured ratio range."""
    if not math.isfinite(ratio):
        raise ValueError("흡광도비는 유한한 값이어야 합니다.")
    curve = calibration_curve(reference)
    ratios = [point.ratio for point in reference]
    # Equivalent scaled inputs may differ at endpoints by binary roundoff.
    nearest = min(ratios, key=lambda value: abs(value - ratio))
    if abs(nearest - ratio) <= 4 * math.ulp(nearest):
        ratio = nearest
    if ratio < ratios[0] or ratio > ratios[-1]:
        return None
    upper = bisect_left(ratios, ratio)
    if ratio == ratios[upper]:
        return reference[upper].concentration
    a, b = reference[upper - 1], reference[upper]
    return float(brentq(lambda concentration: float(curve(concentration)) - ratio,
                        a.concentration, b.concentration, xtol=1e-12))


@dataclass(frozen=True)
class ValidationPoint:
    actual: float
    predicted: float

    @property
    def error(self) -> float:
        return self.predicted - self.actual


@dataclass(frozen=True)
class Validation:
    samples: tuple[ValidationPoint, ...]
    total: int
    excluded_endpoints: int

    @property
    def mae(self) -> float:
        return mean(abs(point.error) for point in self.samples)

    @property
    def rmse(self) -> float:
        return math.sqrt(mean(point.error ** 2 for point in self.samples))

    @property
    def max_error(self) -> float:
        return max(abs(point.error) for point in self.samples)


def validate_reference(reference: list[Point]) -> Validation:
    """Leave one interior concentration out at a time; never score a training fit."""
    _validate_reference(reference)
    if len(reference) < 3:
        raise ValueError("내부 검증에 기준점이 세 개 이상 필요합니다.")
    samples = []
    for index in range(1, len(reference) - 1):
        point = reference[index]
        predicted = estimate(point.ratio, reference[:index] + reference[index + 1:])
        assert predicted is not None  # Retained neighbours bracket every interior point.
        samples.append(ValidationPoint(point.concentration, predicted))
    return Validation(tuple(samples), len(reference), 2)



def read_absorbances(path: Path | str, include_baseline: bool = False) -> tuple[float, ...]:
    """Read one Vernier wavelength–absorbance series, including empty trailing pairs."""
    wavelengths = WAVELENGTHS + ((BASELINE_WAVELENGTH,) if include_baseline else ())
    data = Path(path).read_bytes()
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = data.decode("cp949")
        except UnicodeDecodeError as exc:
            raise ValueError("UTF-8 또는 CP949로 저장한 CSV를 선택하세요.") from exc
    reader = csv.reader(io.StringIO(text))
    header = [label.strip().lower() for label in next(reader, [])]
    pairs = [
        idx for idx in range(len(header) - 1)
        if ("파장" in header[idx] or "wavelength" in header[idx])
        and ("흡광도" in header[idx + 1] or "absorbance" in header[idx + 1])
    ]
    if not pairs:
        raise ValueError("쉼표로 구분된 파장(nm), 흡광도 열이 필요합니다.")

    active = set()
    found = {}
    for row in reader:
        for idx in pairs:
            if len(row) <= idx + 1 or not row[idx + 1].strip():
                continue
            active.add(idx)
            if len(active) > 1:
                raise ValueError("한 번에 한 시료만 분석합니다. 스펙트럼 하나를 선택해 저장하세요.")
            try:
                wave = float(row[idx])
            except ValueError as exc:
                raise ValueError("파장 열에 숫자가 아닌 값이 있습니다.") from exc
            if not math.isfinite(wave):
                raise ValueError("파장 열에 유한하지 않은 값이 있습니다.")
            for target in wavelengths:
                if math.isclose(wave, target, rel_tol=0, abs_tol=0.001):
                    if target in found:
                        raise ValueError(f"{target} nm 측정값이 중복됩니다. 단일 스펙트럼을 선택하세요.")
                    try:
                        found[target] = float(row[idx + 1])
                    except ValueError as exc:
                        raise ValueError(f"{target} nm 흡광도를 숫자로 읽을 수 없습니다.") from exc
    missing = [str(wave) for wave in wavelengths if wave not in found]
    if missing:
        raise ValueError(f"기준 파장 {', '.join(missing)} nm의 측정값이 없습니다.")
    values = tuple(found[wave] for wave in wavelengths)
    a434, a578 = values[:2]
    ratio_from_absorbances(a434, a578)
    if include_baseline and not math.isfinite(values[2]):
        raise ValueError("730.1 nm 흡광도에는 유한한 값이 필요합니다.")
    return values
