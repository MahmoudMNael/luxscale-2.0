from __future__ import annotations

import math

import numpy as np

from app.domain.exceptions import GeometryError
from app.domain.models import Matrix, Patch
from app.services.vector_math import EPS, Vec2, angle_deg, is_convex_polygon, room_polygon, segment_inside_room, visibility_room_polygon


def form_factor(source_patch: Patch, target_patch: Patch) -> float:
    line = (
        target_patch.center[0] - source_patch.center[0],
        target_patch.center[1] - source_patch.center[1],
        target_patch.center[2] - source_patch.center[2],
    )
    distance_sq = line[0] ** 2 + line[1] ** 2 + line[2] ** 2
    if distance_sq < EPS * EPS:
        return 0.0
    distance = math.sqrt(distance_sq)
    cos1 = (line[0] * source_patch.normal[0] + line[1] * source_patch.normal[1] + line[2] * source_patch.normal[2]) / distance
    cos2 = -(line[0] * target_patch.normal[0] + line[1] * target_patch.normal[1] + line[2] * target_patch.normal[2]) / distance
    if cos1 <= 0.0 or cos2 <= 0.0:
        return 0.0
    return source_patch.area * cos1 * cos2 / (math.pi * distance_sq)


def compute_indirect_contribution(
    source_patch: Patch,
    source_illuminance: float,
    target_patch: Patch,
    reflectance: float,
) -> float:
    line = (
        target_patch.center[0] - source_patch.center[0],
        target_patch.center[1] - source_patch.center[1],
        target_patch.center[2] - source_patch.center[2],
    )
    distance = math.sqrt(line[0] ** 2 + line[1] ** 2 + line[2] ** 2)
    if distance < EPS:
        return 0.0
    theta1 = angle_deg(source_patch.normal, line)
    theta2 = angle_deg(target_patch.normal, (-line[0], -line[1], -line[2]))
    if theta1 >= 90.0 or theta2 >= 90.0:
        return 0.0
    return (
        source_illuminance
        * reflectance
        * source_patch.area
        * math.cos(math.radians(theta1))
        * math.cos(math.radians(theta2))
    ) / (math.pi * distance**2)


def _wall_floor_visibility(
    wall_patches: list[Patch],
    floor_patches: list[Patch],
    polygon: list[Vec2],
) -> "np.ndarray | None":
    """Precompute wall->floor plan-view visibility. None = all visible (convex)."""
    import numpy as np

    if not wall_patches or not floor_patches:
        return None
    if is_convex_polygon(polygon):
        return None
    room = visibility_room_polygon(polygon)
    n_wall = len(wall_patches)
    n_floor = len(floor_patches)
    vis = np.ones((n_wall, n_floor), dtype=bool)
    for j, target in enumerate(floor_patches):
        tx, ty = target.center[0], target.center[1]
        for i, source in enumerate(wall_patches):
            if not segment_inside_room(
                (source.center[0], source.center[1]), (tx, ty), room
            ):
                vis[i, j] = False
    return vis


def compute_bounce_values(
    source_patches: list[Patch],
    source_values: list[float] | np.ndarray,
    target_patches: list[Patch],
    reflectance: float,
    room_polygon: list[Vec2] | None = None,
) -> list[float]:
    if len(source_values) != len(source_patches):
        raise GeometryError("Cannot sum matrices with different patch layouts.")
    if not target_patches or not source_patches:
        return [0.0] * len(target_patches)
    src_c = np.array([p.center for p in source_patches], dtype=np.float64)
    src_n = np.array([p.normal for p in source_patches], dtype=np.float64)
    src_a = np.array([p.area for p in source_patches], dtype=np.float64)
    e_src = np.asarray(source_values, dtype=np.float64)
    vis = (
        _wall_floor_visibility(source_patches, target_patches, room_polygon)
        if room_polygon is not None
        else None
    )
    out: list[float] = []
    for j, target in enumerate(target_patches):
        tgt = np.array(target.center, dtype=np.float64)
        tgt_n = np.array(target.normal, dtype=np.float64)
        line = tgt - src_c
        d2 = np.einsum("ij,ij->i", line, line)
        valid = d2 >= EPS * EPS
        d = np.sqrt(np.maximum(d2, EPS * EPS))
        cos1 = (line * src_n).sum(axis=1) / d
        cos2 = -(line * tgt_n).sum(axis=1) / d
        ok = valid & (cos1 > 0.0) & (cos2 > 0.0) & (e_src != 0.0)
        if vis is not None:
            ok = ok & vis[:, j]
        if not bool(ok.any()):
            out.append(0.0)
            continue
        g = np.zeros_like(d2)
        g[ok] = src_a[ok] * cos1[ok] * cos2[ok] / (math.pi * d2[ok])
        out.append(float((e_src[ok] * reflectance) @ g[ok]))
    return out


def compute_indirect_matrix_from_wall(
    wall_patches: list[Patch],
    wall_direct_matrix: Matrix,
    floor_patches: list[Patch],
    reflectance: float,
    *,
    source_wall_id: str,
    patch_size: float,
) -> Matrix:
    if len(wall_direct_matrix.values) != len(wall_patches):
        raise GeometryError("Cannot sum matrices with different patch layouts.")
    return Matrix(
        compute_bounce_values(wall_patches, wall_direct_matrix.values, floor_patches, reflectance),
        {
            "kind": "indirect",
            "surfaceType": "floor",
            "sourceWallId": source_wall_id,
            "patchSize": patch_size,
            "bounces": 1,
            "wallReflectance": reflectance,
        },
    )


def compute_indirect_floor_per_origin(
    all_wall_patches: list[Patch],
    origin_seeds: dict[str, list[float]],
    floor_patches: list[Patch],
    wall_reflectance: float,
    num_bounces: int,
    room_polygon: list[Vec2] | None = None,
) -> dict[str, list[float]]:
    interact = sorted(origin_seeds)
    n_wall = len(all_wall_patches)
    for values in origin_seeds.values():
        if len(values) != n_wall:
            raise GeometryError("Cannot sum matrices with different patch layouts.")
    if num_bounces <= 0 or not floor_patches or not all_wall_patches:
        return {wall_id: [0.0] * len(floor_patches) for wall_id in interact}

    src_c = np.array([p.center for p in all_wall_patches], dtype=np.float64)
    src_n = np.array([p.normal for p in all_wall_patches], dtype=np.float64)
    src_a = np.array([p.area for p in all_wall_patches], dtype=np.float64)
    floor_c = np.array([p.center for p in floor_patches], dtype=np.float64)
    floor_n = np.array([p.normal for p in floor_patches], dtype=np.float64)
    wall_c = src_c
    wall_n = src_n

    cur = np.array([origin_seeds[wall_id] for wall_id in interact], dtype=np.float64)
    accum = np.zeros((len(interact), len(floor_patches)), dtype=np.float64)
    vis = (
        _wall_floor_visibility(all_wall_patches, floor_patches, room_polygon)
        if room_polygon is not None
        else None
    )

    for _ in range(num_bounces):
        for j in range(len(floor_patches)):
            line = floor_c[j] - src_c
            d2 = np.einsum("ij,ij->i", line, line)
            valid = d2 >= EPS * EPS
            d = np.sqrt(np.maximum(d2, EPS * EPS))
            cos1 = (line * src_n).sum(axis=1) / d
            cos2 = -(line * floor_n[j]).sum(axis=1) / d
            ok = valid & (cos1 > 0.0) & (cos2 > 0.0)
            if vis is not None:
                ok = ok & vis[:, j]
            if not bool(ok.any()):
                continue
            g = np.zeros_like(d2)
            g[ok] = src_a[ok] * cos1[ok] * cos2[ok] / (math.pi * d2[ok])
            accum[:, j] += (cur[:, ok] * wall_reflectance) @ g[ok]
        if _ < num_bounces - 1:
            nxt = np.zeros_like(cur)
            active = np.any(cur != 0.0, axis=0)
            for t in range(n_wall):
                line = wall_c[t] - src_c
                d2 = np.einsum("ij,ij->i", line, line)
                valid = d2 >= EPS * EPS
                d = np.sqrt(np.maximum(d2, EPS * EPS))
                cos1 = (line * src_n).sum(axis=1) / d
                cos2 = -(line * wall_n[t]).sum(axis=1) / d
                ok = valid & active & (cos1 > 0.0) & (cos2 > 0.0)
                if not bool(ok.any()):
                    continue
                g = np.zeros_like(d2)
                g[ok] = src_a[ok] * cos1[ok] * cos2[ok] / (math.pi * d2[ok])
                nxt[:, t] = (cur[:, ok] * wall_reflectance) @ g[ok]
            cur = nxt
    return {wall_id: accum[i].tolist() for i, wall_id in enumerate(interact)}
