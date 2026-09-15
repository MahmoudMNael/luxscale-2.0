from __future__ import annotations

import math
import time

import numpy as np

from app.domain.exceptions import GeometryError
from app.domain.models import Matrix, Patch
from app.services.vector_math import EPS, Vec2, angle_deg, is_convex_polygon, room_polygon, segment_inside_room, visibility_polygon

try:
    from shapely.geometry import LineString
except ImportError:  # pragma: no cover
    LineString = None  # type: ignore[assignment]

# ── Plan-view / extrusion assumption ────────────────────────────────────────
# All visibility tests (``_wall_floor_visibility``, ``_source_source_visibility``,
# ``_segment_fraction``, ``segment_inside_room``) operate on 2-D plan-view
# projections only.  Wall heights are treated as prismatic: every wall is a
# full-height rectangle from floor to ceiling with no z-varying obstructions.
# This means the code is exact for prismatic rooms (uniform ceiling, no
# soffits, no furniture, no balconies).  When someone adds a non-prismatic
# element (dropped soffit, mezzanine, shelf, ...), the plan-view projection
# will over-predict visibility — the model will see "around" the obstruction
# because it cannot distinguish z-ranges.  Documented here so future
# contributors know this is a *scoped architectural assumption*, not a bug.
# ────────────────────────────────────────────────────────────────────────────


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


def _source_source_visibility(
    source_patches: list[Patch],
    polygon: list[Vec2],
) -> "tuple[np.ndarray | None, np.ndarray | None]":
    """Plan-view visibility between radiosity source patches.

    Deduped by 2-D position: wall patches stacked vertically share one
    (x, y), and the floor/ceiling grids share xy too, so the segment test
    runs over ~1k unique points instead of ~7k patches. Returns
    ``(uid, vis_uu)`` — per-patch unique-position ids and the symmetric
    (U, U) visibility matrix — or ``(None, None)`` when convex, where
    every pair is visible and the F matrix needs no gating.
    """
    if not source_patches:
        return None, None
    if is_convex_polygon(polygon):
        return None, None
    room = visibility_polygon(polygon)
    xy = np.array(
        [(round(p.center[0], 9), round(p.center[1], 9)) for p in source_patches],
        dtype=np.float64,
    )
    uniq, uid = np.unique(xy, axis=0, return_inverse=True)
    n_unique = len(uniq)
    vis = np.ones((n_unique, n_unique), dtype=bool)
    try:
        from shapely.prepared import prep

        prepared = prep(room)
    except ImportError:  # pragma: no cover
        prepared = None
    ux = uniq[:, 0].tolist()
    uy = uniq[:, 1].tolist()
    for a in range(n_unique):
        ax, ay = ux[a], uy[a]
        for b in range(a + 1, n_unique):
            if prepared is not None:
                if LineString is None or not prepared.covers(
                    LineString([(ax, ay), (ux[b], uy[b])])
                ):
                    vis[a, b] = False
                    vis[b, a] = False
            elif not segment_inside_room((ax, ay), (ux[b], uy[b]), room):
                vis[a, b] = False
                vis[b, a] = False
    return uid, vis


def _segment_fraction(a: Vec2, b: Vec2, room) -> float:
    """Exact plan-view visible fraction: inside-length / total length.

    Never blocks what the exact whole-segment test allows (fast path first);
    otherwise intersects the segment with the room polygon, so grazing notch
    pairs get their true fraction instead of a {0, 0.5, 1} bucket. By default
    only called for significant transfers (see the ``sig`` gate in the ``G``
    build), but ``disable_sig_gate=True`` applies it to all occluded pairs
    for exact gap attribution. Plan-view only — wall heights are ignored,
    consistent with the rest of the visibility model.
    """
    if segment_inside_room(a, b, room):
        return 1.0
    poly = room_polygon(room) if isinstance(room, list) else room
    seg = LineString([a, b]) if LineString is not None else None
    if seg is None or seg.length < EPS:
        return 1.0 if segment_inside_room(a, b, room) else 0.0
    inter = seg.intersection(poly)
    if inter.is_empty:
        return 0.0
    return min(1.0, max(0.0, float(inter.length) / float(seg.length)))


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


def build_transfer_matrix(
    all_source_patches: list[Patch],
    *,
    block_size: int = 512,
    dtype: "np.dtype" = np.float32,
    timings: dict | None = None,
    room_polygon: list[Vec2] | None = None,
) -> "np.ndarray":
    """Source-to-source form-factor matrix: column ``t`` holds transfers to target ``t``.

    Chunked over targets (``block_size`` rows of ``(B, N, 3)`` at a time, so
    peak transient is ~``B*N*3`` float64) instead of a Python per-target loop.
    Floor->floor and ceiling->ceiling pairs are analytically zero (coplanar,
    ``cos`` vanishes) and forced to exactly zero. Values computed in float64,
    stored in ``dtype`` (float32 halves memory for ~7k-source fine meshes).
    When ``room_polygon`` is given and concave, pairs whose plan-view segment
    leaves the room are also zeroed — walls cannot exchange across the notch.
    """
    t0 = time.perf_counter()
    n_src = len(all_source_patches)
    F = np.zeros((n_src, n_src), dtype=dtype)
    if n_src == 0:
        return F
    vis_uid: np.ndarray | None = None
    vis_uu: np.ndarray | None = None
    if room_polygon is not None:
        t_vis = time.perf_counter()
        vis_uid, vis_uu = _source_source_visibility(all_source_patches, room_polygon)
        if timings is not None:
            timings["f_vis_ms"] = (time.perf_counter() - t_vis) * 1000.0
    src_c = np.array([p.center for p in all_source_patches], dtype=np.float64)
    src_n = np.array([p.normal for p in all_source_patches], dtype=np.float64)
    src_a = np.array([p.area for p in all_source_patches], dtype=np.float64)
    kinds = np.array([p.surface_type for p in all_source_patches])
    is_floor = kinds == "floor"
    is_ceiling = kinds == "ceiling"
    inv_pi = 1.0 / math.pi
    for start in range(0, n_src, block_size):
        tb = np.arange(start, min(start + block_size, n_src))
        b = len(tb)
        line = src_c[tb][:, None, :] - src_c[None, :, :]  # (B, N, 3)
        d2 = np.einsum("bnk,bnk->bn", line, line)
        valid = d2 >= EPS * EPS
        d = np.sqrt(np.maximum(d2, EPS * EPS))
        cos1 = np.einsum("bnk,nk->bn", line, src_n) / d
        cos2 = -np.einsum("bnk,bk->bn", line, src_n[tb]) / d
        ok = valid & (cos1 > 0.0) & (cos2 > 0.0)
        if vis_uu is not None and vis_uid is not None:
            ok = ok & vis_uu[vis_uid[tb][:, None], vis_uid[None, :]]
        g = np.zeros((b, n_src), dtype=np.float64)
        a2 = np.broadcast_to(src_a, (b, n_src))
        g[ok] = (a2[ok] * cos1[ok] * cos2[ok] * inv_pi) / d2[ok]
        # Analytic zeros: coplanar horizontal pairs never transfer.
        g[is_floor[tb][:, None] & is_floor[None, :]] = 0.0
        g[is_ceiling[tb][:, None] & is_ceiling[None, :]] = 0.0
        g[np.arange(b), tb] = 0.0  # no self-transfer
        F[:, tb] = g.T.astype(dtype, copy=False)
        del line, d2, d, cos1, cos2, g
    if timings is not None:
        timings["f_build_ms"] = (time.perf_counter() - t0) * 1000.0
    return F


def solve_source_exitance(
    seeds: "np.ndarray",
    transfer: "np.ndarray",
    rho: "np.ndarray",
    *,
    method: str = "neumann",
    num_bounces: int | None = 5,
    tol_lux: float = 0.05,
    max_iters: int = 100,
    timings: dict | None = None,
    floor_gain: float | None = None,
    floor_tol_lux: float | None = None,
) -> "tuple[np.ndarray, int]":
    """Solve ``E = E0 + (E * rho) @ F``. Returns ``(E_src, bounces_used)``.

    ``method="exact"`` uses a dense solve (``E @ A = E0`` with
    ``A = I - diag(rho) @ F``) — only tractable for small ``n_src``; kept as
    the cross-check reference. ``method="neumann"`` iterates
    ``E_{k+1} = E0 + (E_k * rho) @ F`` either ``num_bounces`` times or, when
    ``num_bounces is None``, until convergence (capped at ``max_iters``).
    Convergence is measured on **floor** illuminance when ``floor_gain``
    (max over floor targets of ``Σᵢ Gⱼᵢ·ρᵢ``) and ``floor_tol_lux`` are given:
    per-bounce floor change ``≤ max|ΔE| × floor_gain``, so stopping when that
    bound drops below ``floor_tol_lux`` guarantees the reported floor values
    moved less than the tolerance. Without ``floor_gain`` it falls back to the
    legacy exitance test (``max|ΔE| < tol_lux``), which understates floor
    movement — thousands of sub-tolerance source deltas accumulate downstream.
    """
    t0 = time.perf_counter()
    n_src = transfer.shape[0]
    if method == "exact":
        A = np.eye(n_src, dtype=np.float64) - rho[:, None] * transfer.astype(np.float64)
        E_src = np.linalg.solve(A.T, seeds.T).T
        if timings is not None:
            timings["solve_ms"] = (time.perf_counter() - t0) * 1000.0
        return E_src, -1  # -1 = converged exact solve, not a bounce count
    limit = max_iters if num_bounces is None else num_bounces
    E_src = seeds.copy()
    used = 0
    for _ in range(limit):
        Erho = (E_src * rho[None, :]).astype(np.float32)
        E_new = seeds + (Erho @ transfer).astype(np.float64)
        used += 1
        if num_bounces is None:
            delta = float(np.abs(E_new - E_src).max())
            if floor_gain is not None and floor_tol_lux is not None:
                if delta * floor_gain < floor_tol_lux:
                    E_src = E_new
                    break
            elif delta < tol_lux:
                E_src = E_new
                break
        E_src = E_new
    if timings is not None:
        timings["solve_ms"] = (time.perf_counter() - t0) * 1000.0
    return E_src, used


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
    num_bounces: int | None,
    room_polygon: list[Vec2] | None = None,
    *,
    floor_reflectance: float = 0.0,
    ceiling_reflectance: float = 0.0,
    method: str = "neumann",
    tol_lux: float = 0.05,
    max_iters: int = 100,
    block_size: int = 512,
    out_meta: dict | None = None,
    floor_tol_lux: float | None = None,
    disable_sig_gate: bool = False,
) -> dict[str, list[float]]:
    interact = sorted(origin_seeds)
    n_src = len(all_source_patches)
    n_floor = len(floor_patches)
    for values in origin_seeds.values():
        if len(values) != n_src:
            raise GeometryError("Cannot sum matrices with different patch layouts.")
    if method not in ("neumann", "exact"):
        raise GeometryError(f"Unknown indirect solver method: {method!r}.")
    if num_bounces is not None and num_bounces <= 0 or not floor_patches or not all_source_patches:
        if out_meta is not None:
            out_meta["bounces_used"] = 0
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

    seeds = np.array([origin_seeds[wall_id] for wall_id in interact], dtype=np.float64)
    timings: dict[str, float] = {}
    t_g = time.perf_counter()

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
            if disable_sig_gate:
                occluded = ~vis[:, j]
                if bool(occluded.any()):
                    w = vis[:, j].astype(np.float64)
                    for i in np.where(occluded)[0]:
                        w[i] = _segment_fraction(src_xy[int(i)], tgt_xy[j], vis_room)
                    G[j, :] = g * w
                    continue
                G[j, :] = g * vis[:, j]
            else:
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
    timings["g_ms"] = (time.perf_counter() - t_g) * 1000.0

    # Max floor gain: per-bounce floor change ≤ max|ΔE_src| × floor_gain,
    # so this scalar turns source-exitance deltas into a rigorous floor
    # stopping bound for converged mode.
    floor_gain = float((G * rho[None, :]).sum(axis=1).max()) if n_floor else 0.0

    F = build_transfer_matrix(
        all_source_patches, block_size=block_size, timings=timings,
        room_polygon=room_polygon,
    )
    E_src, bounces_used = solve_source_exitance(
        seeds, F, rho,
        method=method, num_bounces=num_bounces, tol_lux=tol_lux, max_iters=max_iters,
        timings=timings, floor_gain=floor_gain, floor_tol_lux=floor_tol_lux,
    )
    if out_meta is not None:
        out_meta["bounces_used"] = bounces_used
        out_meta["floor_gain"] = floor_gain
        out_meta.update(timings)

    E_floor = (G * rho[None, :]) @ E_src.T
    E_floor = E_floor.T

    return {wall_id: E_floor[i].tolist() for i, wall_id in enumerate(interact)}
