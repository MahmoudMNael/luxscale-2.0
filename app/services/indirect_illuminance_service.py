from __future__ import annotations

import math

import numpy as np

from app.domain.exceptions import GeometryError
from app.domain.models import Matrix, Patch
from app.services.vector_math import EPS, Vec2, angle_deg, is_convex_polygon, room_polygon, segment_inside_room, visibility_polygon


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
    source_patches: list[Patch],
    floor_patches: list[Patch],
    polygon: list[Vec2],
) -> "tuple[np.ndarray | None, object | None]":
    """Precompute source->floor plan-view visibility.

    Returns (visible bool matrix, prepared room) for fractional refinement,
    or (None, None) when all visible (convex).
    """
    if not source_patches or not floor_patches:
        return None, None
    if is_convex_polygon(polygon):
        return None, None
    room = visibility_polygon(polygon)
    n_src = len(source_patches)
    n_floor = len(floor_patches)
    vis = np.ones((n_src, n_floor), dtype=bool)
    for j, target in enumerate(floor_patches):
        tx, ty = target.center[0], target.center[1]
        for i, source in enumerate(source_patches):
            if not segment_inside_room(
                (source.center[0], source.center[1]), (tx, ty), room
            ):
                vis[i, j] = False
    return vis, room


def _segment_fraction(a: Vec2, b: Vec2, room) -> float:
    """Visible fraction of a plan-view segment: 1, 0.5 or 0.

    Never blocks what the exact whole-segment test allows; halves recover
    grazing transfers that a binary gate would drop entirely.
    """
    if segment_inside_room(a, b, room):
        return 1.0
    mid = ((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0)
    fraction = 0.0
    if segment_inside_room(a, mid, room):
        fraction += 0.5
    if segment_inside_room(mid, b, room):
        fraction += 0.5
    return fraction


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
    vis, _ = (
        _wall_floor_visibility(source_patches, target_patches, room_polygon)
        if room_polygon is not None
        else (None, None)
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
    all_source_patches: list[Patch],
    origin_seeds: dict[str, list[float]],
    floor_patches: list[Patch],
    wall_reflectance: float,
    num_bounces: int,
    room_polygon: list[Vec2] | None = None,
    *,
    floor_reflectance: float = 0.0,
    ceiling_reflectance: float = 0.0,
) -> dict[str, list[float]]:
    interact = sorted(origin_seeds)
    n_src = len(all_source_patches)
    n_floor = len(floor_patches)
    for values in origin_seeds.values():
        if len(values) != n_src:
            raise GeometryError("Cannot sum matrices with different patch layouts.")
    if num_bounces <= 0 or not floor_patches or not all_source_patches:
        return {wall_id: [0.0] * n_floor for wall_id in interact}

    rho = np.array(
        [
            wall_reflectance
            if p.surface_type == "wall"
            else floor_reflectance
            if p.surface_type == "floor"
            else ceiling_reflectance
            for p in all_source_patches
        ],
        dtype=np.float64,
    )
    src_c = np.array([p.center for p in all_source_patches], dtype=np.float64)
    src_n = np.array([p.normal for p in all_source_patches], dtype=np.float64)
    src_a = np.array([p.area for p in all_source_patches], dtype=np.float64)
    floor_c = np.array([p.center for p in floor_patches], dtype=np.float64)
    floor_n = np.array([p.normal for p in floor_patches], dtype=np.float64)

    vis, vis_room = (
        _wall_floor_visibility(all_source_patches, floor_patches, room_polygon)
        if room_polygon is not None
        else (None, None)
    )
    src_xy = [(p.center[0], p.center[1]) for p in all_source_patches]
    tgt_xy = [(p.center[0], p.center[1]) for p in floor_patches]

    F = np.zeros((n_src, n_src), dtype=np.float64)
    for t in range(n_src):
        line = src_c[t] - src_c
        d2 = np.einsum("ij,ij->i", line, line)
        valid = d2 >= EPS * EPS
        d = np.sqrt(np.maximum(d2, EPS * EPS))
        cos1 = (line * src_n).sum(axis=1) / d
        cos2 = -(line * src_n[t]).sum(axis=1) / d
        ok = valid & (cos1 > 0.0) & (cos2 > 0.0)
        g = np.zeros_like(d2)
        g[ok] = src_a[ok] * cos1[ok] * cos2[ok] / (math.pi * d2[ok])
        g[t] = 0.0
        F[:, t] = g

    G = np.zeros((n_floor, n_src), dtype=np.float64)
    for j in range(n_floor):
        line = floor_c[j] - src_c
        d2 = np.einsum("ij,ij->i", line, line)
        valid = d2 >= EPS * EPS
        d = np.sqrt(np.maximum(d2, EPS * EPS))
        cos1 = (line * src_n).sum(axis=1) / d
        cos2 = -(line * floor_n[j]).sum(axis=1) / d
        ok = valid & (cos1 > 0.0) & (cos2 > 0.0)
        g = np.zeros_like(d2)
        g[ok] = src_a[ok] * cos1[ok] * cos2[ok] / (math.pi * d2[ok])
        if vis is not None:
            gmax = float(g.max()) if g.size else 0.0
            if gmax > 0.0:
                sig = ~vis[:, j] & (g > 0.01 * gmax)
                if bool(sig.any()):
                    w = vis[:, j].astype(np.float64)
                    for i in np.where(sig)[0]:
                        w[i] = _segment_fraction(src_xy[int(i)], tgt_xy[j], vis_room)
                    G[j, :] = g * w
                    continue
            G[j, :] = g * vis[:, j]
        else:
            G[j, :] = g

    I_mat = np.eye(n_src, dtype=np.float64)
    A = I_mat - rho[:, None] * F
    seeds = np.array([origin_seeds[wall_id] for wall_id in interact], dtype=np.float64)
    E_src = seeds @ np.linalg.inv(A)
    E_floor = (G * rho[None, :]) @ E_src.T
    E_floor = E_floor.T

    return {wall_id: E_floor[i].tolist() for i, wall_id in enumerate(interact)}
