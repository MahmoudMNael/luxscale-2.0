"""Standalone calculation steps + facade.

Each public step is usable without the others unless strictly dependent:

  build_room          verts -> Room (+ resolved heights)          [needs nothing]
  build_eval_grids    Room -> EvalGrids (EN 12464)                [needs S1]
  build_solver_cache  Room + EvalGrids -> SolverCache (mesh)     [needs S1+S2]
  resolve_fixtures    placements + profiles -> Fixture[]         [needs nothing]
  run                 Fixture[] + Room + EvalGrids + Cache
                      -> EngineResult (direct+indirect+totals)    [needs S1..S4]
  calculate           EngineInput + profiles -> EngineResult      [chains all]

Physics is moved verbatim from the former calculate_service god-function;
only fixture generation changed (free placements instead of grid).
"""

from __future__ import annotations

import logging
import time
from dataclasses import replace

from app.app_settings import PATCH_SIZE
from app.domain.exceptions import GeometryError, IesParseError, NoFixturesError
from app.domain.models import Fixture, IESProfile, Matrix, Patch, Room
from app.engine.types import (
    EngineInput,
    EngineResult,
    EvalGrids,
    EvalSummary,
    PhysicsOptions,
    RoomInput,
    SolverCache,
)
from app.services.direct_illuminance_service import compute_direct_matrix
from app.services.fixture_service import build_fixtures
from app.services.geometry_service import (
    apply_interp_weights,
    build_plan_interp_weights,
    build_wall_interp_weights,
    define_room,
    generate_ceiling_evaluation_grid,
    generate_floor_evaluation_grid,
    generate_solver_plan_grid,
    generate_solver_wall_grid,
    generate_wall_evaluation_grid,
    resolve_horizontal_border,
    resolve_solver_cell,
    resolve_wall_border,
)
from app.services.indirect_illuminance_service import compute_indirect_per_target_per_origin
from app.services.matrix_service import apply_maintenance_factor, sum_matrices

_log = logging.getLogger(__name__)


# -- S1: room ---------------------------------------------------------------


def build_room(room: RoomInput) -> tuple[Room, float, float, float]:
    """Define room + resolve (ceiling, mounting, work-plane) heights."""
    ceiling_h = room.ceiling_height
    mount_h = room.mounting_height if room.mounting_height is not None else ceiling_h
    work_z = room.work_plane_height
    if mount_h > ceiling_h + 1e-9:
        raise GeometryError("Mounting height cannot exceed ceiling height.")
    if work_z >= mount_h:
        raise GeometryError("Work plane height must be below the fixture mounting height.")
    return define_room(list(room.polygon), ceiling_h, step=PATCH_SIZE), ceiling_h, mount_h, work_z


# -- S2: evaluation grids ----------------------------------------------------


def build_eval_grids(
    room: Room,
    work_z: float,
    floor_zone: float | None,
    wall_zone: float | None,
) -> EvalGrids:
    """EN 12464 evaluation grids for floor, walls, ceiling."""
    floor_border = resolve_horizontal_border(room.polygon, floor_zone)
    floor_patches, grid_meta = generate_floor_evaluation_grid(room.polygon, work_z, floor_border)
    if not floor_patches:
        raise GeometryError("No floor patches remain after clipping to the polygon.")
    wall_patches: dict[str, list[Patch]] = {}
    wall_metas: dict[str, dict[str, float]] = {}
    for wall in room.walls:
        wb = resolve_wall_border(wall.length, wall.height, wall_zone)
        patches, meta = generate_wall_evaluation_grid(wall, wb)
        wall_patches[wall.id] = patches
        wall_metas[wall.id] = meta
    ceiling_patches, ceiling_meta = generate_ceiling_evaluation_grid(
        room.polygon, room.height, floor_border
    )
    return EvalGrids(
        floor=floor_patches,
        floor_meta=dict(grid_meta),
        floor_border=floor_border,
        walls=wall_patches,
        wall_metas={k: dict(v) for k, v in wall_metas.items()},
        ceiling=ceiling_patches,
        ceiling_meta=dict(ceiling_meta),
        ceiling_border=floor_border,
        work_z=work_z,
    )


# -- S3: solver mesh (fixture-independent, cacheable) -------------------------


def build_solver_cache(
    room: Room,
    eval: EvalGrids,
    ceiling_h: float,
    options: PhysicsOptions,
) -> SolverCache:
    """Radiosity solver mesh + eval interpolation weights. No fixtures needed."""
    solver_cell, solver_estimate, solver_degraded = resolve_solver_cell(
        room.polygon, room.walls, base_cell=options.solver_cell, cap=options.max_solver_patches
    )
    _log.info(
        "solver cell=%.3f estimate=%s degraded=%s", solver_cell, solver_estimate, solver_degraded
    )
    floor_full, floor_full_meta = generate_solver_plan_grid(
        room.polygon, eval.work_z, "floor", "floor", solver_cell, normal=(0.0, 0.0, 1.0)
    )
    ceiling_full, ceiling_full_meta = generate_solver_plan_grid(
        room.polygon, ceiling_h, "ceiling", "ceiling", solver_cell, normal=(0.0, 0.0, -1.0)
    )
    if not floor_full:
        raise GeometryError("No solver patches remain after clipping to the polygon.")
    wall_full: dict[str, list[Patch]] = {}
    wall_full_metas: dict[str, dict[str, float]] = {}
    for wall in room.walls:
        patches, meta = generate_solver_wall_grid(wall, solver_cell)
        wall_full[wall.id] = patches
        wall_full_metas[wall.id] = meta
    all_wall_patches: list[Patch] = [p for wall in room.walls for p in wall_full[wall.id]]
    sources: list[Patch] = [*all_wall_patches, *floor_full, *ceiling_full]
    floor_w = build_plan_interp_weights(
        floor_full,
        floor_full_meta,
        eval.floor,
        eval_dx=float(eval.floor_meta.get("dx", 0.0)),
        eval_dy=float(eval.floor_meta.get("dy", 0.0)),
    )
    ceiling_w = (
        build_plan_interp_weights(
            ceiling_full,
            ceiling_full_meta,
            eval.ceiling,
            eval_dx=float(eval.ceiling_meta.get("dx", 0.0)),
            eval_dy=float(eval.ceiling_meta.get("dy", 0.0)),
        )
        if eval.ceiling and ceiling_full
        else ([0], [], [], 0, len(ceiling_full))
    )
    wall_w: dict[str, tuple] = {}
    for wall in room.walls:
        if eval.walls[wall.id] and wall_full[wall.id]:
            em = eval.wall_metas[wall.id]
            wall_w[wall.id] = build_wall_interp_weights(
                wall,
                wall_full[wall.id],
                wall_full_metas[wall.id],
                eval.walls[wall.id],
                eval_ds=float(em.get("dx", 0.0)),
                eval_dz=float(em.get("dy", 0.0)),
            )
        else:
            wall_w[wall.id] = (
                [0] * (len(eval.walls[wall.id]) + 1),
                [],
                [],
                len(eval.walls[wall.id]),
                len(wall_full[wall.id]),
            )
    return SolverCache(
        floor_full=floor_full,
        floor_full_meta=dict(floor_full_meta),
        ceiling_full=ceiling_full,
        ceiling_full_meta=dict(ceiling_full_meta),
        wall_full=wall_full,
        wall_full_metas={k: dict(v) for k, v in wall_full_metas.items()},
        sources=sources,
        floor_weights=floor_w,
        ceiling_weights=ceiling_w,
        wall_weights=wall_w,
        cell=solver_cell,
        degraded=solver_degraded,
    )


# -- S4: fixtures ------------------------------------------------------------


def resolve_fixtures(
    room: Room,
    placements: list,
    profiles: dict[str, IESProfile],
    mounting_default: float,
    default_ref: str | None = None,
) -> list[Fixture]:
    """Placements + photometry profiles -> domain fixtures (heterogeneous OK)."""
    if not placements:
        raise NoFixturesError("No fixture placements were given.")
    if default_ref is None and len(profiles) == 1:
        default_ref = next(iter(profiles))
    for placement in placements:
        ref = placement.ies_ref or default_ref
        if ref is None or ref not in profiles:
            raise IesParseError(
                f"Fixture '{placement.id}' references unknown photometry "
                f"'{placement.ies_ref}' (no default IES file given)."
            )
    return build_fixtures(room.polygon, placements, profiles, mounting_default, default_ref)


# -- S5+S6+S7+S8: physics run -------------------------------------------------


def run(
    fixtures: list[Fixture],
    room: Room,
    eval: EvalGrids,
    cache: SolverCache,
    options: PhysicsOptions,
) -> EngineResult:
    """Direct + interreflected + maintained totals + EN 12464 summaries."""
    if not fixtures:
        raise NoFixturesError("No fixtures fall inside the room polygon.")
    c0 = options.c0_offset_deg
    floor_cell = eval.floor[0].size
    full_cell = cache.floor_full[0].size if cache.floor_full else floor_cell

    # Solver-mesh direct (seeds for radiosity).
    raw_floor_direct_full = (
        {
            fixture.id: compute_direct_matrix(
                fixture,
                cache.floor_full,
                "floor",
                patch_size=full_cell,
                room_polygon=room.polygon,
                c0_offset_deg=c0,
            )
            for fixture in fixtures
        }
        if cache.floor_full
        else {}
    )
    raw_wall_direct_full: dict[str, dict[str, Matrix]] = {}
    for wall in room.walls:
        patches = cache.wall_full[wall.id]
        if not patches:
            raw_wall_direct_full[wall.id] = {}
            continue
        cell = patches[0].size
        per_fix: dict[str, Matrix] = {}
        for fixture in fixtures:
            m = compute_direct_matrix(
                fixture,
                patches,
                "wall",
                patch_size=cell,
                wall_id=wall.id,
                room_polygon=room.polygon,
                c0_offset_deg=c0,
            )
            m = Matrix(m.values, {**m.metadata, "patchSize": cell, "wallId": wall.id})
            per_fix[fixture.id] = m
        raw_wall_direct_full[wall.id] = per_fix
    ceiling_full_cell = cache.ceiling_full[0].size if cache.ceiling_full else full_cell
    raw_ceiling_direct_full = (
        {
            fixture.id: compute_direct_matrix(
                fixture,
                cache.ceiling_full,
                "ceiling",
                patch_size=ceiling_full_cell,
                room_polygon=room.polygon,
                c0_offset_deg=c0,
            )
            for fixture in fixtures
        }
        if cache.ceiling_full
        else {}
    )

    offsets: dict[str, int] = {}
    pos = 0
    for wall in room.walls:
        offsets[wall.id] = pos
        pos += len(cache.wall_full[wall.id])
    floor_offset = pos
    pos += len(cache.floor_full)
    ceiling_offset = pos

    seeds: dict[str, list[float]] = {}
    for wall in room.walls:
        per_fix = raw_wall_direct_full.get(wall.id, {})
        if not per_fix or not cache.wall_full[wall.id]:
            continue
        total_wall = sum_matrices(list(per_fix.values()))
        seed = [0.0] * len(cache.sources)
        start = offsets[wall.id]
        seed[start : start + len(total_wall.values)] = list(total_wall.values)
        seeds[wall.id] = seed
    if raw_floor_direct_full:
        total_floor_direct = sum_matrices(list(raw_floor_direct_full.values()))
        seed = [0.0] * len(cache.sources)
        seed[floor_offset : floor_offset + len(total_floor_direct.values)] = list(
            total_floor_direct.values
        )
        seeds["floor"] = seed
    if raw_ceiling_direct_full and cache.ceiling_full:
        total_ceiling_direct = sum_matrices(list(raw_ceiling_direct_full.values()))
        seed = [0.0] * len(cache.sources)
        seed[ceiling_offset : ceiling_offset + len(total_ceiling_direct.values)] = list(
            total_ceiling_direct.values
        )
        seeds["ceiling"] = seed

    targets_full: dict[str, list[Patch]] = {
        "floor": cache.floor_full,
        "ceiling": cache.ceiling_full,
    }
    for wall in room.walls:
        targets_full[wall.id] = cache.wall_full[wall.id]

    mf = options.maintenance_factor
    applied_bounces = options.bounces if options.bounces > 0 and seeds else 0
    if seeds and applied_bounces > 0:
        per_target_full = compute_indirect_per_target_per_origin(
            cache.sources,
            seeds,
            targets_full,
            options.wall_reflectance,
            applied_bounces,
            room.polygon,
            floor_reflectance=options.floor_reflectance,
            ceiling_reflectance=options.ceiling_reflectance,
        )
    else:
        per_target_full = {
            tid: {oid: [0.0] * len(tp) for oid in seeds} for tid, tp in targets_full.items()
        }
        if not seeds:
            per_target_full = {tid: {} for tid in targets_full}

    def _indirect_matrices(
        tid: str, tgt: list[Patch], cell: float, weights: tuple
    ) -> dict[str, Matrix]:
        out: dict[str, Matrix] = {}
        per_origin = per_target_full.get(tid, {})
        for oid, vals in per_origin.items():
            out[oid] = Matrix(
                apply_interp_weights(list(vals), weights),
                {
                    "kind": "indirect",
                    "surfaceType": "floor"
                    if tid == "floor"
                    else ("ceiling" if tid == "ceiling" else "wall"),
                    "targetId": tid,
                    "sourceWallId": oid,
                    "patchSize": cell,
                    "bounces": applied_bounces,
                    "wallReflectance": options.wall_reflectance,
                    "floorReflectance": options.floor_reflectance,
                    "ceilingReflectance": options.ceiling_reflectance,
                    "radiosity": "solver-interp",
                },
            )
        return out

    # Exact analytic direct at the evaluation points.
    raw_floor_direct = (
        {
            fixture.id: compute_direct_matrix(
                fixture,
                eval.floor,
                "floor",
                patch_size=floor_cell,
                room_polygon=room.polygon,
                c0_offset_deg=c0,
            )
            for fixture in fixtures
        }
        if eval.floor
        else {}
    )
    raw_wall_direct: dict[str, dict[str, Matrix]] = {}
    for wall in room.walls:
        patches = eval.walls[wall.id]
        if not patches:
            raw_wall_direct[wall.id] = {}
            continue
        cell = patches[0].size
        raw_wall_direct[wall.id] = {
            fixture.id: compute_direct_matrix(
                fixture,
                patches,
                "wall",
                patch_size=cell,
                wall_id=wall.id,
                room_polygon=room.polygon,
                c0_offset_deg=c0,
            )
            for fixture in fixtures
        }
    raw_ceiling_direct = (
        {
            fixture.id: compute_direct_matrix(
                fixture,
                eval.ceiling,
                "ceiling",
                patch_size=eval.ceiling[0].size if eval.ceiling else full_cell,
                room_polygon=room.polygon,
                c0_offset_deg=c0,
            )
            for fixture in fixtures
        }
        if eval.ceiling
        else {}
    )

    raw_indirect_floor = _indirect_matrices("floor", eval.floor, floor_cell, cache.floor_weights)
    raw_indirect_ceiling = _indirect_matrices(
        "ceiling",
        eval.ceiling,
        eval.ceiling[0].size if eval.ceiling else 0.0,
        cache.ceiling_weights,
    )
    raw_indirect_walls: dict[str, dict[str, Matrix]] = {}
    for wall in room.walls:
        patches = eval.walls[wall.id]
        cell = patches[0].size if patches else 0.0
        raw_indirect_walls[wall.id] = _indirect_matrices(
            wall.id, patches, cell, cache.wall_weights[wall.id]
        )

    direct_floor = {fid: apply_maintenance_factor(m, mf) for fid, m in raw_floor_direct.items()}
    direct_walls = {
        wid: {fid: apply_maintenance_factor(m, mf) for fid, m in per_fix.items()}
        for wid, per_fix in raw_wall_direct.items()
    }
    direct_ceiling = {
        fid: apply_maintenance_factor(m, mf) for fid, m in raw_ceiling_direct.items()
    }
    indirect_floor = {
        oid: apply_maintenance_factor(m, mf) for oid, m in raw_indirect_floor.items()
    }
    indirect_ceiling = {
        oid: apply_maintenance_factor(m, mf) for oid, m in raw_indirect_ceiling.items()
    }
    indirect_walls = {
        wid: {oid: apply_maintenance_factor(m, mf) for oid, m in per_origin.items()}
        for wid, per_origin in raw_indirect_walls.items()
    }

    raw_total_floor = (
        sum_matrices([*raw_floor_direct.values(), *raw_indirect_floor.values()])
        if (raw_floor_direct or raw_indirect_floor)
        else Matrix([0.0] * len(eval.floor), {"kind": "raw-total"})
    )
    total_floor = apply_maintenance_factor(raw_total_floor, mf)
    if eval.ceiling:
        raw_total_ceiling = (
            sum_matrices([*raw_ceiling_direct.values(), *raw_indirect_ceiling.values()])
            if (raw_ceiling_direct or raw_indirect_ceiling)
            else Matrix([0.0] * len(eval.ceiling), {"kind": "raw-total"})
        )
        total_ceiling = apply_maintenance_factor(raw_total_ceiling, mf)
    else:
        total_ceiling = Matrix([], {"kind": "total", "surfaceType": "ceiling"})
    total_walls: dict[str, Matrix] = {}
    for wall in room.walls:
        patches = eval.walls[wall.id]
        if not patches:
            total_walls[wall.id] = Matrix([], {"kind": "total", "surfaceType": "wall"})
            continue
        parts = [
            *raw_wall_direct.get(wall.id, {}).values(),
            *raw_indirect_walls.get(wall.id, {}).values(),
        ]
        raw_total = (
            sum_matrices(parts)
            if parts
            else Matrix([0.0] * len(patches), {"kind": "raw-total"})
        )
        total_walls[wall.id] = apply_maintenance_factor(raw_total, mf)

    wall_evaluations = {}
    for wall in room.walls:
        patches = eval.walls[wall.id]
        vals = total_walls[wall.id].values
        if patches and vals:
            wall_evaluations[wall.id] = _summarize(
                vals, eval.wall_metas[wall.id].get("border", 0.0)
            )
    ceiling_evaluation = (
        _summarize(total_ceiling.values, eval.ceiling_border)
        if eval.ceiling and total_ceiling.values
        else None
    )
    return EngineResult(
        fixtures=fixtures,
        eval=eval,
        direct_floor=direct_floor,
        direct_walls=direct_walls,
        direct_ceiling=direct_ceiling,
        indirect_floor=indirect_floor,
        indirect_ceiling=indirect_ceiling,
        indirect_walls=indirect_walls,
        total_floor=total_floor,
        total_ceiling=total_ceiling,
        total_walls=total_walls,
        evaluation=_summarize(total_floor.values, eval.floor_border),
        ceiling_evaluation=ceiling_evaluation,
        wall_evaluations=wall_evaluations,
        bounces=applied_bounces,
        ceiling_height=room.height,
        mounting_height=(
            fixtures[0].position[2] + fixtures[0].ies_profile.height / 2.0 if fixtures else room.height
        ),
        solver_cell=cache.cell,
        solver_degraded=cache.degraded,
        options=options,
    )


def _summarize(values: list[float], wall_zone: float) -> EvalSummary:
    lo, hi = min(values), max(values)
    avg = sum(values) / len(values)
    return EvalSummary(
        average=avg,
        minimum=lo,
        maximum=hi,
        uniformity=(lo / avg if avg > 0 else 0.0),
        min_index=values.index(lo),
        max_index=values.index(hi),
        count=len(values),
    )


# -- facade ------------------------------------------------------------------


def calculate(
    payload: EngineInput,
    profiles: dict[str, IESProfile],
    *,
    options: PhysicsOptions | None = None,
    default_ref: str | None = None,
) -> EngineResult:
    """Full chain S1→S8 for one room + one placement list."""
    started = time.perf_counter()
    opts = options or PhysicsOptions()
    room, ceiling_h, mount_h, work_z = build_room(payload.room)
    _log.info(
        "start vertices=%s ceiling=%s mounting=%s fixtures=%s",
        len(payload.room.polygon),
        ceiling_h,
        mount_h,
        len(payload.placements),
    )
    eval = build_eval_grids(room, work_z, payload.room.floor_zone, payload.room.wall_zone)
    cache = build_solver_cache(room, eval, ceiling_h, opts)
    _log.info(
        "geometry walls=%s floor=%s ceiling=%s",
        len(room.walls),
        len(eval.floor),
        len(eval.ceiling),
    )
    fixtures = resolve_fixtures(room, payload.placements, profiles, mount_h, default_ref)
    _log.info("fixtures=%s", len(fixtures))
    result = run(fixtures, room, eval, cache, opts)
    # Response-level mounting = room default; per-fixture overrides stay in positions.
    result = replace(result, mounting_height=mount_h)
    _log.info(
        "success duration_ms=%.1f bounces=%s",
        (time.perf_counter() - started) * 1000,
        result.bounces,
    )
    return result
