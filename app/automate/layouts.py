"""Grid-strategy layouts: (spacing, symmetric offsets, rotation) -> placements.

The engine only ever sees free placements; this module is one replaceable
strategy for generating them (regular grid). Advanced strategies (genetic,
manual edit, wall-wash rows) plug in beside it without touching the engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.models import FixturePlacement
from app.services.fixture_service import axis_positions
from app.services.vector_math import EPS, point_in_polygon


@dataclass(frozen=True)
class LayoutSpec:
    sx: float
    sy: float
    ox: float  # symmetric: beginning == ending
    oy: float
    rotation: float


def frange(lo: float, hi: float, step: float) -> list[float]:
    """Inclusive float range (edge-case-correct: always emits hi)."""
    if step <= EPS:
        return [lo]
    out: list[float] = []
    v = lo
    while v < hi - EPS:
        out.append(v)
        v += step
    out.append(hi)
    return out


# Auto-spacing rule (used when search.spacingX/Y is left empty).
# EDIT HERE to change what "auto" means.
AUTO_SPACING_MIN = 1.5
AUTO_SPACING_STEP = 0.5
AUTO_SPACING_STEP_HIGH = 1.0
AUTO_SPACING_HEIGHT_THRESHOLD = 3.0


def auto_spacing_range(
    polygon: list[tuple[float, float]],
    mount_h: float,
    shr_max: float,
    combo_multiplier: int,
    max_candidates: int,
) -> tuple[float, float, float]:
    """(min, max, step) derived from room size + mounting height.

    - max: tightest of the SHR cap (`shr_max x mount_h`) and the longest
      room-bbox side (never wider than the room itself).
    - min: fixed floor (`AUTO_SPACING_MIN`); tiny rooms where max < min
      collapse to a single spacing instead of 422ing.
    - step: `AUTO_SPACING_STEP` (0.5m) for mount_h <= 3.0m, or
      `AUTO_SPACING_STEP_HIGH` (1.0m) for mount_h > 3.0m (vast/high spaces),
      doubled until `len(x) x len(y) x combo_multiplier <= max_candidates`.
    """
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    longest = max(max(xs) - min(xs), max(ys) - min(ys))
    hi = min(shr_max * mount_h, longest)
    lo_floor = max(AUTO_SPACING_MIN, round(0.5 * mount_h, 1)) if mount_h >= 4.0 else AUTO_SPACING_MIN
    lo = min(lo_floor, hi)
    step = AUTO_SPACING_STEP_HIGH if mount_h > AUTO_SPACING_HEIGHT_THRESHOLD else AUTO_SPACING_STEP
    for _ in range(20):  # safety bound; normally exits on the first pass
        n = len(frange(lo, hi, step)) ** 2 * max(combo_multiplier, 1)
        if n <= max_candidates:
            break
        step *= 2.0
    return (round(lo, 3), round(hi, 3), round(step, 3))


def enumerate_layouts(
    polygon: list[tuple[float, float]],
    mount_h: float,
    sx_vals: list[float],
    sy_vals: list[float],
    offset_fractions: list[float],
    rotations: list[float],
    min_wall_clearance: float,
    shr_max: float,
) -> tuple[list[LayoutSpec], dict[str, int]]:
    """All (sx, sy, frac, rot) combos minus SHR/clearance prunes.

    ponytail: symmetric offsets only (centered grids). Asymmetric
    begin/end offsets stay available via the /calculate placements path;
    add them here when a real room needs wall-wash tuning.
    """
    pruned = {"shr": 0, "clearance": 0}
    out: list[LayoutSpec] = []
    for sx in sx_vals:
        for sy in sy_vals:
            if sx > shr_max * mount_h + EPS or sy > shr_max * mount_h + EPS:
                pruned["shr"] += 1
                continue
            for frac in offset_fractions:
                ox, oy = frac * sx, frac * sy
                if ox < min_wall_clearance - EPS or oy < min_wall_clearance - EPS:
                    pruned["clearance"] += 1
                    continue
                for rotation in rotations:
                    out.append(LayoutSpec(sx=sx, sy=sy, ox=ox, oy=oy, rotation=rotation))
    return out, pruned


def placements_for_layout(
    polygon: list[tuple[float, float]],
    spec: LayoutSpec,
) -> list[FixturePlacement]:
    """LayoutSpec -> free placements (same ordering/ids as the legacy grid)."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    placements: list[FixturePlacement] = []
    n = 1
    for y in axis_positions(ymin, ymax, spec.sy, spec.oy, spec.oy):
        for x in axis_positions(xmin, xmax, spec.sx, spec.ox, spec.ox):
            if not point_in_polygon((x, y), polygon):
                continue
            placements.append(FixturePlacement(id=f"F{n}", x=x, y=y, rotation=spec.rotation))
            n += 1
    return placements
