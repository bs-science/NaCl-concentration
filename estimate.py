"""NaCl estimates from the 434.2 and 578.3 nm measurements of Tris–mCP samples."""

from __future__ import annotations

import csv
import io
import math
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from statistics import mean


REFERENCE_FILE = Path(__file__).with_name("reference.csv")
RUN_DATES = ("20261029", "20261102", "20261105")
CONCENTRATIONS = (0.0, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6)
WAVELENGTHS = (434.2, 578.3)


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

    @property
    def ratio(self) -> float:
        return ratio_from_absorbances(self.a434, self.a578)


def load_runs() -> list[list[Point]]:
    groups = {day: [] for day in RUN_DATES}
    with REFERENCE_FILE.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            groups[row["run_date"]].append(Point(
                float(row["concentration_M"]), float(row["A434_2"]), float(row["A578_3"])
            ))
    for run in groups.values():
        run.sort(key=lambda point: point.concentration)
        if tuple(point.concentration for point in run) != CONCENTRATIONS:
            raise ValueError("기준 파일의 농도 조건 8개를 확인하세요.")
    return list(groups.values())


def estimate(ratio: float, reference: list[Point]) -> float | None:
    """Invert a strictly increasing set of reference points without extrapolating."""
    if not math.isfinite(ratio):
        raise ValueError("흡광도비는 유한한 값이어야 합니다.")
    ratios = [point.ratio for point in reference]
    if len(reference) < 2 or any(lo >= hi for lo, hi in zip(ratios, ratios[1:])):
        raise ValueError("흡광도비가 순서대로 증가하는 기준점이 두 개 이상 필요합니다.")
    if ratio < ratios[0] or ratio > ratios[-1]:
        return None
    upper = bisect_left(ratios, ratio)
    if ratio == ratios[upper]:
        return reference[upper].concentration
    a, b = reference[upper - 1], reference[upper]
    fraction = (ratio - a.ratio) / (b.ratio - a.ratio)
    return a.concentration + fraction * (b.concentration - a.concentration)


def validate_runs(runs: list[list[Point]]) -> list[tuple[str, int, int, float]]:
    ref = runs[2]
    results = []
    internal = []
    for index in range(1, len(ref) - 1):
        point = ref[index]
        predicted = estimate(point.ratio, ref[:index] + ref[index + 1:])
        assert predicted is not None  # An omitted interior point is still bracketed.
        internal.append(abs(predicted - point.concentration))
    results.append(("3차 내부 보간", len(internal), len(internal), mean(internal)))
    for label, run in zip(("1차 자료", "2차 자료"), runs[:2]):
        errors = []
        for point in run:
            predicted = estimate(point.ratio, ref)
            if predicted is not None:
                errors.append(abs(predicted - point.concentration))
        results.append((label, len(errors), len(run), mean(errors) if errors else math.nan))
    return results


def read_absorbances(path: Path | str) -> tuple[float, float]:
    """Read one Vernier wavelength–absorbance series, including empty trailing pairs."""
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
            for target in WAVELENGTHS:
                if math.isclose(wave, target, rel_tol=0, abs_tol=0.001):
                    if target in found:
                        raise ValueError(f"{target} nm 측정값이 중복됩니다. 단일 스펙트럼을 선택하세요.")
                    try:
                        found[target] = float(row[idx + 1])
                    except ValueError as exc:
                        raise ValueError(f"{target} nm 흡광도를 숫자로 읽을 수 없습니다.") from exc
    missing = [str(wave) for wave in WAVELENGTHS if wave not in found]
    if missing:
        raise ValueError(f"기준 파장 {', '.join(missing)} nm의 측정값이 없습니다.")
    a434, a578 = (found[wave] for wave in WAVELENGTHS)
    ratio_from_absorbances(a434, a578)
    return a434, a578
