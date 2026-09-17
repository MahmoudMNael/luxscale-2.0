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
    from shapely.geometry import LineString
    from shapely.prepared import prep

    room = visibility_polygon(polygon)
    prepared = prep(room)
    n_src = len(source_patches)
    n_floor = len(floor_patches)
    vis = np.ones((n_src, n_floor), dtype=bool)
    for j, target in enumerate(floor_patches):
        b = (target.center[0], target.center[1])
        for i, source in enumerate(source_patches):
            if not prepared.covers(
                LineString([(source.center[0], source.center[1]), b])
            ):
                vis[i, j] = False
    return vis, room


def _source_source_visibility(
    source_patches: list[Patch],
    polygon: list[Vec2],
) -> "np.ndarray | None":
    """Plan-view visibility between radiosity sources (Relux parity).

    The F matrix previously assumed all patches see each other, leaking
    inter-reflection through concave notches (22% of pairs in the L-case).
    Binary mask with the same 3 mm buffered room as G; None when convex.
    """
    from shapely.geometry import LineString
    from shapely.prepared import prep

    if not source_patches or polygon is None:
        return None
    if is_convex_polygon(polygon):
        return None
    room = visibility_polygon(polygon)
    prepared = prep(room)
    n = len(source_patches)
    # Plan-view visibility depends only on XY: patches stacked vertically
    # share XY, so test unique positions (walls: ns, not ns*nz).
    key_of: dict[tuple[float, float], int] = {}
    uniq: list[tuple[float, float]] = []
    idx: list[int] = []
    for p in source_patches:
        key = (round(p.center[0], 9), round(p.center[1], 9))
        u = key_of.get(key)
        if u is None:
            u = len(uniq)
            key_of[key] = u
            uniq.append(key)
        idx.append(u)
    m = len(uniq)
    vis_u = np.ones((m, m), dtype=bool)
    for t in range(m):
        b = uniq[t]
        for i in range(m):
            if i == t:
                vis_u[i, t] = False
                continue
            if not prepared.covers(LineString([uniq[i], b])):
                vis_u[i, t] = False
    ii = np.asarray(idx, dtype=np.int64)
    return vis_u[ii][:, ii]


def _union_plan_visibility(
    all_source_patches: list[Patch],
    targets: dict[str, list[Patch]],
    polygon: list[Vec2] | None,
) -> "tuple[np.ndarray, np.ndarray | None, dict[tuple[float, float], int]]":
    """Shared plan-view visibility over unique XY (Relux solver scale).

    Returns ``(src_idx, vis_union_or_None, key_of)``. Targets index into the
    same union, so F and all G sets cost ~mu^2 prepared-covers tests total.
    ``None` when convex/unset (all visible)."""
    from shapely.geometry import LineString
    from shapely.prepared import prep

    n_src = len(all_source_patches)
    if not all_source_patches or polygon is None or is_convex_polygon(polygon):
        return np.zeros(n_src, dtype=np.int64), None, {}
    key_of: dict[tuple[float, float], int] = {}
    uniq: list[tuple[float, float]] = []

    def _take(x: float, y: float) -> int:
        key = (round(x, 9), round(y, 9))
        u = key_of.get(key)
        if u is None:
            u = len(uniq)
            key_of[key] = u
            uniq.append(key)
        return u

    src_idx = np.array([_take(p.center[0], p.center[1]) for p in all_source_patches], dtype=np.int64)
    for tp in targets.values():
        for p in tp:
            _take(p.center[0], p.center[1])
    room = visibility_polygon(polygon)
    prepared = prep(room)
    m = len(uniq)
    vis = np.ones((m, m), dtype=bool)
    for t in range(m):
        b = uniq[t]
        row = vis[:, t]
        for i in range(m):
            if i == t:
                continue
            if not prepared.covers(LineString([uniq[i], b])):
                row[i] = False
    return src_idx, vis, key_of


def _tangent_frames(normals: "np.ndarray") -> "tuple[np.ndarray, np.ndarray]":
    """Orthonormal tangent pair per patch normal for near-field subdivision.

    Uses world-up (0,0,1), falling back to (1,0,0) for horizontal patches
    so wall (vertical-normal) and floor/ceiling frames stay well-defined.
    """
    n = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), EPS)
    up = np.tile(np.array([0.0, 0.0, 1.0]), (len(n), 1))
    flat = np.abs(n[:, 2]) > 0.9
    up[flat] = np.array([1.0, 0.0, 0.0])
    t1 = np.cross(up, n)
    t1 /= np.maximum(np.linalg.norm(t1, axis=1, keepdims=True), EPS)
    t2 = np.cross(n, t1)
    return t1, t2


def _refine_close_transfers(
    g: "np.ndarray",
    src_c: "np.ndarray",
    src_n: "np.ndarray",
    src_a: "np.ndarray",
    src_t1: "np.ndarray",
    src_t2: "np.ndarray",
    tgt_point: "np.ndarray",
    tgt_normal: "np.ndarray",
    tgt_area: float,
    tgt_t1: "np.ndarray",
    tgt_t2: "np.ndarray",
    close: "np.ndarray",
) -> None:
    """In-place 2x2 area-averaged correction for near-field point pairs.

    Point-to-point ``A*cos1*cos2/(pi*d^2)`` overestimates when patches are
    closer than ~2 patch sizes (worst at shared wall/floor edges). Splitting
    both patches into 2x2 sub-patches and averaging the 16 sub-transfers
    recovers most of the area integral at negligible cost since only close
    pairs take this path. (Higher orders were trialled: the enclosure
    conservation below renormalizes source rows, cancelling their extra
    effect on room averages.)
    """
    if not bool(close.any()):
        return
    ds_t = math.sqrt(max(tgt_area, EPS))
    tt1 = np.asarray(tgt_t1, dtype=np.float64).reshape(3)
    tt2 = np.asarray(tgt_t2, dtype=np.float64).reshape(3)
    tp = np.asarray(tgt_point, dtype=np.float64).reshape(3)
    tn = np.asarray(tgt_normal, dtype=np.float64).reshape(3)
    off_t = np.array([-0.25 * ds_t, 0.25 * ds_t])
    tq = (
        tp[None, None, :]
        + off_t[:, None, None] * tt1[None, None, :]
        + off_t[None, :, None] * tt2[None, None, :]
    ).reshape(-1, 3)
    idx = np.nonzero(close)[0]
    for i in idx:
        ds = math.sqrt(max(float(src_a[i]), EPS))
        st1 = np.asarray(src_t1[i], dtype=np.float64).reshape(3)
        st2 = np.asarray(src_t2[i], dtype=np.float64).reshape(3)
        sc = np.asarray(src_c[i], dtype=np.float64).reshape(3)
        o = np.array([-0.25 * ds, 0.25 * ds])
        sp = (
            sc[None, None, :]
            + o[:, None, None] * st1[None, None, :]
            + o[None, :, None] * st2[None, None, :]
        ).reshape(-1, 3)
        diff = tq[:, None, :] - sp[None, :, :]
        d2 = np.einsum("qpd,qpd->qp", diff, diff)
        valid = d2 >= EPS * EPS
        d = np.sqrt(np.maximum(d2, EPS * EPS))
        sn = src_n[i]
        c1 = (diff * sn).sum(axis=2) / d
        c2 = -(diff * tn).sum(axis=2) / d
        ok = valid & (c1 > 0.0) & (c2 > 0.0)
        sub = np.zeros_like(d2)
        sub[ok] = (float(src_a[i]) / 4.0) * c1[ok] * c2[ok] / (math.pi * d2[ok])
        g[i] = sub.sum() / 4.0


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
    out = compute_indirect_per_target_per_origin(
        all_source_patches, origin_seeds, {"__floor__": floor_patches},
        wall_reflectance, num_bounces, room_polygon,
        floor_reflectance=floor_reflectance, ceiling_reflectance=ceiling_reflectance,
    )
    return {origin: out["__floor__"][origin] for origin in origin_seeds}


def compute_indirect_per_target_per_origin(
    all_source_patches: list[Patch],
    origin_seeds: dict[str, list[float]],
    targets: dict[str, list[Patch]],
    wall_reflectance: float,
    num_bounces: int,
    room_polygon: list[Vec2] | None = None,
    *,
    floor_reflectance: float = 0.0,
    ceiling_reflectance: float = 0.0,
) -> dict[str, dict[str, list[float]]]:
    interact = sorted(origin_seeds)
    n_src = len(all_source_patches)
    for values in origin_seeds.values():
        if len(values) != n_src:
            raise GeometryError("Cannot sum matrices with different patch layouts.")
    if num_bounces <= 0 or not all_source_patches:
        return {tid: {oid: [0.0] * len(tp) for oid in interact} for tid, tp in targets.items()}

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

    # One shared plan-view visibility over the union of unique XY positions
    # (walls share XY along their stack; floor/ceiling share plan XY).
    # Slices serve both F and every G target set: ~mu^2 shapely tests total
    # instead of n_src^2 + n_src*n_tgt_all.
    uni_src_idx, uni_vis, uni_key_of = _union_plan_visibility(all_source_patches, targets, room_polygon)
    if uni_vis is not None:
        src_vis = uni_vis[uni_src_idx][:, uni_src_idx]
        np.fill_diagonal(src_vis, False)
    else:
        src_vis = None

    src_t1, src_t2 = _tangent_frames(src_n)
    src_ds = np.sqrt(np.maximum(src_a, EPS))
    F = np.zeros((n_src, n_src), dtype=np.float64)
    for t in range(n_src):
        line = src_c[t] - src_c
        d2 = np.einsum("ij,ij->i", line, line)
        valid = d2 >= EPS * EPS
        d = np.sqrt(np.maximum(d2, EPS * EPS))
        cos1 = (line * src_n).sum(axis=1) / d
        cos2 = -(line * src_n[t]).sum(axis=1) / d
        ok = valid & (cos1 > 0.0) & (cos2 > 0.0)
        if src_vis is not None:
            ok = ok & src_vis[:, t]
        g = np.zeros_like(d2)
        g[ok] = src_a[ok] * cos1[ok] * cos2[ok] / (math.pi * d2[ok])
        g[t] = 0.0
        close = ok & (d < 2.0 * np.maximum(src_ds, src_ds[t]))
        close[t] = False
        _refine_close_transfers(
            g, src_c, src_n, src_a, src_t1, src_t2,
            src_c[t], src_n[t], float(src_a[t]), src_t1[t], src_t2[t], close,
        )
        F[:, t] = g

    # Enclosure conservation: standard row sums Σ_t F[i,t]*A_t/A_i must be
    # ≤ 1, but point sampling leaks (measured mean ≈ 1.05 on 0.3 m meshes),
    # compounding ~5% excess per bounce. Scale each source row back so the
    # room keeps exactly the energy it reflects (closed rooms sum to 1).
    with np.errstate(divide="ignore", invalid="ignore"):
        row_sum = (F * src_a[None, :]).sum(axis=1) / np.maximum(src_a, EPS)
    conserve = np.minimum(1.0, 1.0 / np.maximum(row_sum, EPS))
    F = F * conserve[:, None]

    seeds = np.array([origin_seeds[oid] for oid in interact], dtype=np.float64)
    # Neumann series honoring NUM_BOUNCES: E = seeds + (E*rho)@F iterated
    # (num_bounces-1) times, final transfer to targets adds the last bounce.
    # num_bounces=1 → single bounce; large N converges to the closed form.
    E_src = seeds
    for _ in range(max(0, num_bounces - 1)):
        E_src = seeds + (E_src * rho[None, :]) @ F

    out: dict[str, dict[str, list[float]]] = {}
    for tid, tgt_patches in targets.items():
        n_tgt = len(tgt_patches)
        if n_tgt == 0:
            out[tid] = {oid: [] for oid in interact}
            continue
        tgt_c = np.array([p.center for p in tgt_patches], dtype=np.float64)
        tgt_n = np.array([p.normal for p in tgt_patches], dtype=np.float64)
        tgt_a = np.array([p.area for p in tgt_patches], dtype=np.float64)
        tgt_t1, tgt_t2 = _tangent_frames(tgt_n)
        if uni_vis is not None:
            t_idx = np.array(
                [uni_key_of[(round(p.center[0], 9), round(p.center[1], 9))] for p in tgt_patches],
                dtype=np.int64,
            )
            vis = uni_vis[uni_src_idx][:, t_idx]
        else:
            vis = None
        G = np.zeros((n_tgt, n_src), dtype=np.float64)
        for j in range(n_tgt):
            line = tgt_c[j] - src_c
            d2 = np.einsum("ij,ij->i", line, line)
            valid = d2 >= EPS * EPS
            d = np.sqrt(np.maximum(d2, EPS * EPS))
            cos1 = (line * src_n).sum(axis=1) / d
            cos2 = -(line * tgt_n[j]).sum(axis=1) / d
            ok = valid & (cos1 > 0.0) & (cos2 > 0.0)
            g = np.zeros_like(d2)
            g[ok] = src_a[ok] * cos1[ok] * cos2[ok] / (math.pi * d2[ok])
            close = ok & (d < 2.0 * np.maximum(src_ds, math.sqrt(max(float(tgt_a[j]), EPS))))
            _refine_close_transfers(
                g, src_c, src_n, src_a, src_t1, src_t2,
                tgt_c[j], tgt_n[j], float(tgt_a[j]), tgt_t1[j], tgt_t2[j], close,
            )
            if vis is not None:
                G[j, :] = g * vis[:, j]
            else:
                G[j, :] = g
        # Same source-side conservation as F: transfers leaving source i
        # carry conserve[i].
        E_tgt = (((G * conserve[None, :]) * rho[None, :]) @ E_src.T).T
        out[tid] = {oid: E_tgt[i].tolist() for i, oid in enumerate(interact)}
    return out
