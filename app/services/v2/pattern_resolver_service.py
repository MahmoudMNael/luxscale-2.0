"""Parametric array pattern resolver for LuxScale v2.

Resolves high-level parametric patterns (grid, staggered, linear, circumference)
into concrete FixturePlacement instances with 1:1 mathematical parity to the frontend.
Supports per-slot overrides for variant, rotation, tilt, and disabled status.
"""

from __future__ import annotations

import math
from itertools import product
from typing import Any
from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import FixturePlacement
from app.schemas.geometry import Point2D
from app.services.vector_math import point_in_polygon


def polygon_bounding_box(polygon: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    return min(xs), max(xs), min(ys), max(ys)


class PatternSlotOverride(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    variantId: str | None = Field(default=None, alias="variant_id")
    rotationOffset: float = Field(default=0.0, alias="rotation_offset")
    tiltAngleOffset: float = Field(default=0.0, alias="tilt_angle_offset")
    disabled: bool = False


class ParametricPatternDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = "PAT-01"
    name: str = "Array Pattern"
    type: str = Field(..., description="'grid', 'staggered', 'linear', or 'circumference'")
    variantId: str | None = Field(default=None, alias="variant_id")
    iesRef: str | None = Field(default=None, alias="ies_ref")
    mountHeight: float = Field(default=2.8, gt=0, alias="mount_height")
    baseRotation: float = Field(default=0.0, alias="base_rotation")
    baseTilt: float = Field(default=0.0, ge=0, le=180, alias="base_tilt")

    # Grid / Staggered parameters
    gridType: str = Field(default="count", alias="grid_type")  # 'count' | 'spacing'
    countX: int = Field(default=3, ge=1, alias="count_x")
    countY: int = Field(default=3, ge=1, alias="count_y")
    spacingX: float = Field(default=2.0, gt=0.1, alias="spacing_x")
    spacingY: float = Field(default=2.0, gt=0.1, alias="spacing_y")
    offsetFraction: float = Field(default=0.5, ge=0, le=1, alias="offset_fraction")
    autoCenter: bool = Field(default=True, alias="auto_center")

    # Circumference / Perimeter parameters
    wallOffset: float = Field(default=0.8, gt=0.05, alias="wall_offset")
    perimeterSpacing: float = Field(default=2.0, gt=0.1, alias="perimeter_spacing")

    # Linear parameters
    lineStart: dict[str, float] | None = Field(default=None, alias="line_start")
    lineEnd: dict[str, float] | None = Field(default=None, alias="line_end")
    count: int | None = None
    spacing: float | None = None

    # Custom slot overrides: slot_key -> override
    slotOverrides: dict[str, PatternSlotOverride] = Field(default_factory=dict, alias="slot_overrides")


def resolve_pattern(
    pattern: ParametricPatternDto,
    polygon: list[tuple[float, float]],
    default_mount_height: float,
) -> list[FixturePlacement]:
    """Resolves a single pattern into a list of engine FixturePlacement instances."""
    pt_type = pattern.type.lower()
    z = pattern.mountHeight if pattern.mountHeight > 0 else default_mount_height
    base_rot = pattern.baseRotation
    base_tilt = pattern.baseTilt
    def_var = pattern.variantId
    def_ies = pattern.iesRef

    if pt_type == "grid":
        return _resolve_grid(pattern, polygon, z, base_rot, base_tilt, def_var, def_ies)
    elif pt_type == "staggered":
        return _resolve_staggered(pattern, polygon, z, base_rot, base_tilt, def_var, def_ies)
    elif pt_type == "linear":
        return _resolve_linear(pattern, polygon, z, base_rot, base_tilt, def_var, def_ies)
    elif pt_type == "circumference":
        return _resolve_circumference(pattern, polygon, z, base_rot, base_tilt, def_var, def_ies)
    return []


def _apply_slot_override(
    base_placement: FixturePlacement,
    slot_key: str,
    overrides: dict[str, PatternSlotOverride],
) -> FixturePlacement | None:
    override = overrides.get(slot_key)
    if override and override.disabled:
        return None

    rot = base_placement.rotation
    tilt = getattr(base_placement, "tilt_angle", 0.0)
    var_id = base_placement.variant_id

    if override:
        if override.variantId:
            var_id = override.variantId
        if override.rotationOffset:
            rot = (rot + override.rotationOffset) % 360.0
        if override.tiltAngleOffset:
            tilt = max(0.0, min(180.0, tilt + override.tiltAngleOffset))

    # Aim direction computed from rotation and tilt
    tilt_rad = math.radians(tilt)
    rot_rad = math.radians(rot)
    aim = (
        math.sin(tilt_rad) * math.cos(rot_rad),
        math.sin(tilt_rad) * math.sin(rot_rad),
        -math.cos(tilt_rad),
    )

    return FixturePlacement(
        id=base_placement.id,
        x=base_placement.x,
        y=base_placement.y,
        z=base_placement.z,
        rotation=rot,
        tilt_angle=tilt,
        aim_direction=aim,
        variant_id=var_id,
        ies_ref=base_placement.ies_ref,
    )


def _resolve_grid(
    pattern: ParametricPatternDto,
    polygon: list[tuple[float, float]],
    z: float,
    base_rot: float,
    base_tilt: float,
    def_var: str | None,
    def_ies: str | None,
) -> list[FixturePlacement]:
    xmin, xmax, ymin, ymax = polygon_bounding_box(polygon)
    span_x = max(0.01, xmax - xmin)
    span_y = max(0.01, ymax - ymin)

    if pattern.gridType == "count":
        cx = max(1, pattern.countX)
        cy = max(1, pattern.countY)
        frac = max(0.0, min(1.0, pattern.offsetFraction))
        denom_x = cx - 1 + 2 * frac if cx > 1 else (2 * frac or 1)
        sx = span_x / denom_x
        dx = sx * frac
        xs = [xmin + dx + i * sx for i in range(cx)]

        denom_y = cy - 1 + 2 * frac if cy > 1 else (2 * frac or 1)
        sy = span_y / denom_y
        dy = sy * frac
        ys = [ymin + dy + j * sy for j in range(cy)]
    else:
        sx = max(0.2, pattern.spacingX)
        sy = max(0.2, pattern.spacingY)
        cx = max(1, int(span_x // sx))
        cy = max(1, int(span_y // sy))
        dx = (span_x - (cx - 1) * sx) / 2 if pattern.autoCenter else sx / 2
        dy = (span_y - (cy - 1) * sy) / 2 if pattern.autoCenter else sy / 2
        xs = [xmin + dx + i * sx for i in range(cx)]
        ys = [ymin + dy + j * sy for j in range(cy)]

    placements: list[FixturePlacement] = []
    idx = 1
    for r, y in enumerate(ys):
        for c, x in enumerate(xs):
            cx_round = round(x, 3)
            cy_round = round(y, 3)
            if point_in_polygon((cx_round, cy_round), polygon):
                slot_key = f"r{r}_c{c}"
                base = FixturePlacement(
                    id=f"{pattern.id}_{idx}",
                    x=cx_round,
                    y=cy_round,
                    z=z,
                    rotation=base_rot,
                    tilt_angle=base_tilt,
                    variant_id=def_var,
                    ies_ref=def_ies,
                )
                idx += 1
                final = _apply_slot_override(base, slot_key, pattern.slotOverrides)
                if final is not None:
                    placements.append(final)

    return placements


def _resolve_staggered(
    pattern: ParametricPatternDto,
    polygon: list[tuple[float, float]],
    z: float,
    base_rot: float,
    base_tilt: float,
    def_var: str | None,
    def_ies: str | None,
) -> list[FixturePlacement]:
    xmin, xmax, ymin, ymax = polygon_bounding_box(polygon)
    span_x = max(0.01, xmax - xmin)
    span_y = max(0.01, ymax - ymin)

    if pattern.gridType == "count":
        cx = max(1, pattern.countX)
        cy = max(1, pattern.countY)
        frac = max(0.0, min(1.0, pattern.offsetFraction))
        denom_x = cx - 1 + 2 * frac if cx > 1 else (2 * frac or 1)
        sx = span_x / denom_x
        dx = sx * frac
        xs = [xmin + dx + i * sx for i in range(cx)]

        denom_y = cy - 1 + 2 * frac if cy > 1 else (2 * frac or 1)
        sy = span_y / denom_y
        dy = sy * frac
        ys = [ymin + dy + j * sy for j in range(cy)]
    else:
        sx = max(0.2, pattern.spacingX)
        sy = max(0.2, pattern.spacingY)
        cx = max(1, int(span_x // sx))
        cy = max(1, int(span_y // sy))
        dx = (span_x - (cx - 1) * sx) / 2 if pattern.autoCenter else sx / 2
        dy = (span_y - (cy - 1) * sy) / 2 if pattern.autoCenter else sy / 2
        xs = [xmin + dx + i * sx for i in range(cx)]
        ys = [ymin + dy + j * sy for j in range(cy)]

    shift = sx / 2
    placements: list[FixturePlacement] = []
    idx = 1
    for r, y in enumerate(ys):
        row_shift = shift if r % 2 == 1 else 0.0
        for c, base_x in enumerate(xs):
            x = base_x + row_shift
            if row_shift > 0 and x > span_x + xmin - 0.1:
                x -= span_x
            cx_round = round(x, 3)
            cy_round = round(y, 3)
            if point_in_polygon((cx_round, cy_round), polygon):
                slot_key = f"r{r}_c{c}"
                base = FixturePlacement(
                    id=f"{pattern.id}_{idx}",
                    x=cx_round,
                    y=cy_round,
                    z=z,
                    rotation=base_rot,
                    tilt_angle=base_tilt,
                    variant_id=def_var,
                    ies_ref=def_ies,
                )
                idx += 1
                final = _apply_slot_override(base, slot_key, pattern.slotOverrides)
                if final is not None:
                    placements.append(final)

    return placements


def _resolve_linear(
    pattern: ParametricPatternDto,
    polygon: list[tuple[float, float]],
    z: float,
    base_rot: float,
    base_tilt: float,
    def_var: str | None,
    def_ies: str | None,
) -> list[FixturePlacement]:
    start = pattern.lineStart or {"x": 1.0, "y": 1.0}
    end = pattern.lineEnd or {"x": 5.0, "y": 1.0}

    dx = end["x"] - start["x"]
    dy = end["y"] - start["y"]
    length = math.hypot(dx, dy)
    if length < 0.1:
        return []

    # Number of points
    if pattern.count is not None and pattern.count >= 1:
        count = pattern.count
    elif pattern.spacing is not None and pattern.spacing > 0.1:
        count = max(2, int(length // pattern.spacing) + 1)
    else:
        count = 3

    ux = dx / length
    uy = dy / length
    step = length / (count - 1) if count > 1 else 0.0
    line_angle_deg = math.degrees(math.atan2(dy, dx))

    placements: list[FixturePlacement] = []
    for i in range(count):
        dist = i * step
        x = round(start["x"] + ux * dist, 3)
        y = round(start["y"] + uy * dist, 3)
        slot_key = f"idx_{i}"
        base = FixturePlacement(
            id=f"{pattern.id}_{i + 1}",
            x=x,
            y=y,
            z=z,
            rotation=(base_rot + line_angle_deg) % 360.0,
            tilt_angle=base_tilt,
            variant_id=def_var,
            ies_ref=def_ies,
        )
        final = _apply_slot_override(base, slot_key, pattern.slotOverrides)
        if final is not None:
            placements.append(final)

    return placements


def _resolve_circumference(
    pattern: ParametricPatternDto,
    polygon: list[tuple[float, float]],
    z: float,
    base_rot: float,
    base_tilt: float,
    def_var: str | None,
    def_ies: str | None,
) -> list[FixturePlacement]:
    if len(polygon) < 3:
        return []

    offset = max(0.1, pattern.wallOffset)
    spacing = max(0.5, pattern.perimeterSpacing)

    placements: list[FixturePlacement] = []
    idx = 1

    n_vertices = len(polygon)
    for i in range(n_vertices):
        p1 = polygon[i]
        p2 = polygon[(i + 1) % n_vertices]
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        edge_len = math.hypot(dx, dy)
        if edge_len < 0.3:
            continue

        tx = dx / edge_len
        ty = dy / edge_len

        # Inward normal
        nx = -ty
        ny = tx
        mid_x = (p1[0] + p2[0]) / 2
        mid_y = (p1[1] + p2[1]) / 2
        if not point_in_polygon((mid_x + nx * 0.05, mid_y + ny * 0.05), polygon):
            nx = -nx
            ny = -ny

        wall_angle_deg = (math.degrees(math.atan2(dy, dx)) + 360.0) % 360.0

        num_fixtures = max(1, int(edge_len // spacing))
        edge_step = edge_len / (num_fixtures + 1)

        for s in range(1, num_fixtures + 1):
            t_dist = s * edge_step
            center_x = p1[0] + tx * t_dist + nx * offset
            center_y = p1[1] + ty * t_dist + ny * offset

            clean_x = round(center_x, 3)
            clean_y = round(center_y, 3)

            if point_in_polygon((clean_x, clean_y), polygon):
                slot_key = f"w{i}_s{s}"
                base = FixturePlacement(
                    id=f"{pattern.id}_{idx}",
                    x=clean_x,
                    y=clean_y,
                    z=z,
                    rotation=(base_rot + wall_angle_deg) % 360.0,
                    tilt_angle=base_tilt,
                    variant_id=def_var,
                    ies_ref=def_ies,
                )
                idx += 1
                final = _apply_slot_override(base, slot_key, pattern.slotOverrides)
                if final is not None:
                    placements.append(final)

    return placements
