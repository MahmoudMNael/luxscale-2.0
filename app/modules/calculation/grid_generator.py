from __future__ import annotations

import math
from dataclasses import dataclass
from app.services.vector_math import EPS, en12464_spacing, point_in_polygon

Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]


@dataclass(frozen=True)
class GridResult:
    nx: int
    ny: int
    spacing_x: float
    spacing_y: float
    wall_zone: float
    work_plane_height: float
    points: list[Vec3]


def generate_calculation_grid(
    polygon: list[Vec2],
    workplane_height: float = 0.85,
    wall_margin: float = 0.5,
    pitch: float | None = None,
) -> GridResult:
    """Generates normative evaluation grid coordinates inside a polygon per EN 12464-1."""
    if len(polygon) < 3:
        raise ValueError("Polygon must have at least 3 vertices")

    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    span_x = max_x - min_x
    span_y = max_y - min_y

    # Calculate actual inset boundary
    actual_margin = min(wall_margin, span_x * 0.45, span_y * 0.45)
    inset_min_x = min_x + actual_margin
    inset_max_x = max_x - actual_margin
    inset_min_y = min_y + actual_margin
    inset_max_y = max_y - actual_margin

    inset_span_x = max(0.1, inset_max_x - inset_min_x)
    inset_span_y = max(0.1, inset_max_y - inset_min_y)

    # Determine spacing: custom pitch or EN 12464-1 normative spacing
    longest_dim = max(span_x, span_y)
    target_spacing = pitch if pitch and pitch > 0.05 else en12464_spacing(longest_dim)
    target_spacing = max(0.1, min(2.0, target_spacing))

    nx = max(1, math.ceil(inset_span_x / target_spacing - EPS))
    ny = max(1, math.ceil(inset_span_y / target_spacing - EPS))

    spacing_x = inset_span_x / nx
    spacing_y = inset_span_y / ny

    points: list[Vec3] = []
    # Grid centers
    for iy in range(ny):
        y = inset_min_y + (iy + 0.5) * spacing_y
        for ix in range(nx):
            x = inset_min_x + (ix + 0.5) * spacing_x
            if point_in_polygon((x, y), polygon):
                points.append((round(x, 4), round(y, 4), round(workplane_height, 4)))

    return GridResult(
        nx=nx,
        ny=ny,
        spacing_x=round(spacing_x, 4),
        spacing_y=round(spacing_y, 4),
        wall_zone=round(actual_margin, 4),
        work_plane_height=round(workplane_height, 4),
        points=points,
    )
