from __future__ import annotations

from app.domain.exceptions import GeometryError
from app.domain.models import FloorSurface, Patch, Room, Wall, WallSurface
from app.services.vector_math import (
    EPS,
    centroid_2d,
    clip_rect_to_polygon,
    norm,
    polygon_area,
    signed_area,
)

Vec2 = tuple[float, float]


def _close(vertices: list[Vec2]) -> list[Vec2]:
    if len(vertices) >= 2 and vertices[0] == vertices[-1]:
        return vertices[:-1]
    return list(vertices)


def _segments(start: float, end: float, size: float, handling: str) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    pos = start
    while end - pos > EPS:
        if end - pos + EPS >= size:
            out.append((pos, pos + size))
            pos += size
            continue
        if handling == "clip":
            break
        if handling == "pad":
            out.append((pos, pos + size))
            break
        out.append((pos, end))
        break
    return out


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
    edge_handling: str = "shrink",
    *,
    plane_z: float,
) -> list[Patch]:
    size = 1.0 if patch_size is None else patch_size
    if isinstance(surface, FloorSurface):
        return _floor_patches(surface, size, edge_handling, plane_z)
    return _wall_patches(surface, size, edge_handling)


def _floor_patches(surface: FloorSurface, size: float, edge_handling: str, plane_z: float) -> list[Patch]:
    xs = [p[0] for p in surface.polygon]
    ys = [p[1] for p in surface.polygon]
    patches: list[Patch] = []
    n = 0
    for y0, y1 in _segments(min(ys), max(ys), size, edge_handling):
        for x0, x1 in _segments(min(xs), max(xs), size, edge_handling):
            for ring in clip_rect_to_polygon((x0, y0, x1, y1), surface.polygon):
                area = polygon_area(ring)
                if area <= EPS:
                    continue
                cx, cy = centroid_2d(ring)
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


def _wall_patches(surface: WallSurface, size: float, edge_handling: str) -> list[Patch]:
    dx = surface.end[0] - surface.start[0]
    dy = surface.end[1] - surface.start[1]
    length = norm((dx, dy))
    if length < EPS:
        raise GeometryError(f"Wall {surface.wall_id} has zero length.")
    ux, uy = dx / length, dy / length
    patches: list[Patch] = []
    n = 0
    for z0, z1 in _segments(0.0, surface.height, size, edge_handling):
        for s0, s1 in _segments(0.0, length, size, edge_handling):
            s_mid, z_mid = (s0 + s1) / 2.0, (z0 + z1) / 2.0
            patches.append(
                Patch(
                    id=f"{surface.wall_id}-{n}",
                    surface_type="wall",
                    parent_id=surface.wall_id,
                    center=(surface.start[0] + ux * s_mid, surface.start[1] + uy * s_mid, z_mid),
                    normal=(surface.normal[0], surface.normal[1], 0.0),
                    area=(s1 - s0) * (z1 - z0),
                    size=size,
                )
            )
            n += 1
    return patches
