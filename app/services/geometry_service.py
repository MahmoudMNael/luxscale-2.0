from __future__ import annotations

import math

from app.domain.exceptions import GeometryError
from app.domain.models import FloorSurface, Patch, Room, Wall, WallSurface
from app.services.vector_math import (
    EPS,
    en12464_spacing,
    inset_rings,
    norm,
    point_in_polygon,
    signed_area,
)

Vec2 = tuple[float, float]


def _close(vertices: list[Vec2]) -> list[Vec2]:
    if len(vertices) >= 2 and vertices[0] == vertices[-1]:
        return vertices[:-1]
    return list(vertices)


def _segments(start: float, end: float, size: float) -> list[tuple[float, float]]:
    span = end - start
    if span <= EPS or size <= EPS:
        return []
    n = max(1, math.ceil(span / size - EPS))
    actual = span / n
    return [(start + i * actual, start + (i + 1) * actual) for i in range(n)]


def define_room(vertices: list[Vec2], height: float, step: float = 1.0) -> Room:
    polygon = _close(vertices)
    if len(polygon) < 3 or abs(signed_area(polygon)) <= EPS:
        raise GeometryError("Room polygon must have non-zero area.")
    walls: list[Wall] = []
    for i, start in enumerate(polygon):
        end = polygon[(i + 1) % len(polygon)]
        length = norm((end[0] - start[0], end[1] - start[1]))
        wall_id = f"W{i + 1}"
        if length < EPS:
            raise GeometryError(f"Wall {wall_id} has zero length.")
        dx, dy = (end[0] - start[0]) / length, (end[1] - start[1]) / length
        # CCW polygon: rotate edge 90° left for inward; CW: opposite.
        if signed_area(polygon) > 0:
            normal = (-dy, dx)
        else:
            normal = (dy, -dx)
        walls.append(Wall(id=wall_id, start=start, end=end, length=length, normal=normal, height=height))
    return Room(polygon=polygon, height=height, walls=walls, step=step)


def generate_patches(
    surface: FloorSurface | WallSurface,
    patch_size: float | None = None,
    *,
    plane_z: float,
    border: float = 0.0,
) -> list[Patch]:
    if isinstance(surface, FloorSurface):
        return _floor_patches(surface, plane_z, border)
    size = 1.0 if patch_size is None else patch_size
    return _wall_patches(surface, size)


def _floor_patches(surface: FloorSurface, plane_z: float, border: float) -> list[Patch]:
    domains = inset_rings(surface.polygon, border)
    if not domains:
        return []
    xs = [p[0] for ring in domains for p in ring]
    ys = [p[1] for ring in domains for p in ring]
    width, height = max(xs) - min(xs), max(ys) - min(ys)
    if width <= EPS or height <= EPS:
        return []
    spacing = en12464_spacing(max(width, height))
    if spacing <= EPS:
        return []
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    nx = max(1, math.ceil(width / spacing - EPS))
    ny = max(1, math.ceil(height / spacing - EPS))
    dx, dy = width / nx, height / ny
    area = dx * dy
    size = max(dx, dy)
    patches: list[Patch] = []
    n = 0
    for j in range(ny):
        cy = ymin + (j + 0.5) * dy
        for i in range(nx):
            cx = xmin + (i + 0.5) * dx
            if not any(point_in_polygon((cx, cy), domain) for domain in domains):
                continue
            patches.append(
                Patch(
                    id=f"floor-{n}",
                    surface_type="floor",
                    parent_id="floor",
                    center=(cx, cy, plane_z),
                    normal=(0.0, 0.0, 1.0),
                    area=area,
                    size=size,
                )
            )
            n += 1
    return patches


def _wall_patches(surface: WallSurface, size: float) -> list[Patch]:
    dx = surface.end[0] - surface.start[0]
    dy = surface.end[1] - surface.start[1]
    length = norm((dx, dy))
    if length < EPS:
        raise GeometryError(f"Wall {surface.wall_id} has zero length.")
    ux, uy = dx / length, dy / length
    patches: list[Patch] = []
    n = 0
    for z0, z1 in _segments(0.0, surface.height, size):
        for s0, s1 in _segments(0.0, length, size):
            s_mid, z_mid = (s0 + s1) / 2.0, (z0 + z1) / 2.0
            patches.append(
                Patch(
                    id=f"{surface.wall_id}-{n}",
                    surface_type="wall",
                    parent_id=surface.wall_id,
                    center=(surface.start[0] + ux * s_mid, surface.start[1] + uy * s_mid, z_mid),
                    normal=(surface.normal[0], surface.normal[1], 0.0),
                    area=(s1 - s0) * (z1 - z0),
                    size=max(s1 - s0, z1 - z0),
                )
            )
            n += 1
    return patches
