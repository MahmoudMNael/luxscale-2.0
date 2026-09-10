from __future__ import annotations

from app.domain.exceptions import IesParseError
from app.domain.models import IESProfile
from app.services.vector_math import EPS, wrap_deg


def load_ies(ies_text: str) -> IESProfile:
    if not ies_text.strip():
        raise IesParseError("IES candela table is missing or incomplete.")
    lines = ies_text.splitlines()
    tilt_at = next((i for i, line in enumerate(lines) if line.strip().upper().startswith("TILT")), None)
    if tilt_at is None:
        raise IesParseError("IES file must declare TILT=NONE.")
    tilt_value = lines[tilt_at].split("=", 1)[-1].strip().upper()
    if tilt_value != "NONE":
        raise IesParseError("IES file must declare TILT=NONE.")

    nums: list[float] = []
    for line in lines[tilt_at + 1 :]:
        for tok in line.replace(",", " ").split():
            try:
                nums.append(float(tok))
            except ValueError as exc:
                raise IesParseError("IES candela table is missing or incomplete.") from exc

    if len(nums) < 13:
        raise IesParseError("IES candela table is missing or incomplete.")
    n_v, n_h = int(nums[3]), int(nums[4])
    if n_v < 1 or n_h < 1:
        raise IesParseError("IES candela table is missing or incomplete.")
    if int(nums[5]) != 1:
        raise IesParseError("IES photometric type must be Type C (1).")
    needed = 13 + n_v + n_h + n_v * n_h
    if len(nums) < needed:
        raise IesParseError("IES candela table is missing or incomplete.")

    i = 13
    vertical = nums[i : i + n_v]
    i += n_v
    horizontal = nums[i : i + n_h]
    i += n_h
    raw = nums[i : i + n_v * n_h]
    table = [[0.0] * n_h for _ in range(n_v)]
    k = 0
    for h in range(n_h):
        for v in range(n_v):
            table[v][h] = raw[k]
            k += 1
    feet = 0.3048 if int(nums[6]) == 1 else 1.0
    return IESProfile(
        vertical,
        horizontal,
        table,
        nums[2],
        nums[10],
        nums[11],
        abs(nums[7]) * feet,
        abs(nums[8]) * feet,
        abs(nums[9]) * feet,
    )


def get_candela(profile: IESProfile, theta_vertical_deg: float, phi_horizontal_deg: float) -> float:
    iv0, iv1, tv = _bracket(profile.vertical_angles, theta_vertical_deg)
    scale = profile.multiplier * profile.ballast_factor * profile.ballast_lamp_factor
    if len(profile.horizontal_angles) == 1:
        value = _lerp(profile.candela_table[iv0][0], profile.candela_table[iv1][0], tv)
        return value * scale
    ih0, ih1, th = _phi_bracket(profile.horizontal_angles, phi_horizontal_deg)
    lo = _lerp(profile.candela_table[iv0][ih0], profile.candela_table[iv0][ih1], th)
    hi = _lerp(profile.candela_table[iv1][ih0], profile.candela_table[iv1][ih1], th)
    return _lerp(lo, hi, tv) * scale


def _lerp(a: float, b: float, t: float) -> float:
    return a * (1.0 - t) + b * t


def _bracket(angles: list[float], value: float) -> tuple[int, int, float]:
    if value <= angles[0]:
        return 0, 0, 0.0
    if value >= angles[-1]:
        last = len(angles) - 1
        return last, last, 0.0
    for i in range(len(angles) - 1):
        if angles[i] <= value <= angles[i + 1]:
            span = angles[i + 1] - angles[i]
            t = 0.0 if abs(span) < EPS else (value - angles[i]) / span
            return i, i + 1, t
    last = len(angles) - 1
    return last, last, 0.0


def _phi_bracket(angles: list[float], phi: float) -> tuple[int, int, float]:
    phi = wrap_deg(phi)
    n = len(angles)
    step = (angles[-1] - angles[0]) / (n - 1) if n > 1 else 0.0
    circular = ((angles[0] + 360.0) - angles[-1]) <= step * 1.5 + EPS
    if not circular:
        return _bracket(angles, phi)
    extended = angles + [angles[0] + 360.0]
    sample = phi if phi >= angles[0] else phi + 360.0
    i0, i1, t = _bracket(extended, sample)
    return i0 % n, i1 % n, t
