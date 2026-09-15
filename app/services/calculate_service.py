from __future__ import annotations

import logging
import time

from app.app_settings import C0_ORIENTATION_OFFSET_DEG, CEILING_REFLECTANCE_FACTOR, FLOOR_REFLECTANCE_FACTOR, MAINTENANCE_FACTOR, NUM_BOUNCES, PATCH_SIZE, WALL_REFLECTANCE_FACTOR, WORK_PLANE_HEIGHT
from app.domain.exceptions import GeometryError
from app.domain.models import Fixture, Matrix, Patch, Vec3, WallSurface
from app.schemas.calculate import CalculateRequest, CalculateResponse, EvaluationDto, FixtureDto
from app.schemas.geometry import PatchDto, Vec3Dto
from app.schemas.matrix import MatrixDto
from app.services.direct_illuminance_service import compute_direct_matrix
from app.services.fixture_service import generate_fixture_grid, luminous_opening
from app.services.geometry_service import define_room, generate_ceiling_evaluation_grid, generate_floor_evaluation_grid, generate_wall_evaluation_grid, resolve_horizontal_border, resolve_wall_border
from app.services.ies_service import load_ies
from app.services.indirect_illuminance_service import compute_indirect_per_target_per_origin
from app.services.matrix_service import apply_maintenance_factor, sum_matrices

_log = logging.getLogger(__name__)


def calculate(payload: CalculateRequest, ies_text: str) -> CalculateResponse:
    started = time.perf_counter()
    ceiling_h = payload.ceilingHeight if payload.ceilingHeight is not None else payload.height
    mount_h = payload.mountingHeight if payload.mountingHeight is not None else ceiling_h
    work_z = payload.workPlaneHeight if payload.workPlaneHeight is not None else WORK_PLANE_HEIGHT
    if mount_h > ceiling_h + 1e-9:
        raise GeometryError("Mounting height cannot exceed ceiling height.")
    if work_z >= mount_h:
        raise GeometryError("Work plane height must be below the fixture mounting height.")
    _log.info(
        "start vertices=%s height=%s ceiling=%s mounting=%s spacing=(%s,%s) offsets_x=(%s,%s) offsets_y=(%s,%s)",
        len(payload.polygon),
        payload.height,
        ceiling_h,
        mount_h,
        payload.grid.x.spacing,
        payload.grid.y.spacing,
        payload.grid.x.offset_beginning,
        payload.grid.x.offset_ending,
        payload.grid.y.offset_beginning,
        payload.grid.y.offset_ending,
    )
    room = define_room([(p.x, p.y) for p in payload.polygon], ceiling_h, step=PATCH_SIZE)
    floor_override = payload.floorZone
    wall_override = payload.wallZone
    floor_border = resolve_horizontal_border(room.polygon, floor_override)
    ceiling_border = floor_border
    floor_patches, grid_meta = generate_floor_evaluation_grid(room.polygon, work_z, floor_border)
    if not floor_patches:
        raise GeometryError("No floor patches remain after clipping to the polygon.")
    wall_patches: dict[str, list[Patch]] = {}
    wall_metas: dict[str, dict[str, float]] = {}
    for wall in room.walls:
        wb = resolve_wall_border(wall.length, wall.height, wall_override)
        patches, meta = generate_wall_evaluation_grid(wall, wb)
        wall_patches[wall.id] = patches
        wall_metas[wall.id] = meta
    floor_cell = floor_patches[0].size
    ceiling_patches, ceiling_meta = generate_ceiling_evaluation_grid(room.polygon, ceiling_h, ceiling_border)
    _log.info(
        "geometry walls=%s floor=%s@%.3f ceiling=%s@%.3f wall_patches=%s",
        len(room.walls),
        len(floor_patches),
        floor_border,
        len(ceiling_patches),
        ceiling_border,
        {wid: len(pts) for wid, pts in wall_patches.items()},
    )
    ies = load_ies(ies_text)
    fixtures = generate_fixture_grid(
        room, payload.grid, mount_h, ies, rotation=payload.luminaireRotation
    )
    _log.info("fixtures=%s rotation=%s", len(fixtures), payload.luminaireRotation)

    raw_floor_direct = {
        fixture.id: compute_direct_matrix(
            fixture, floor_patches, "floor", patch_size=floor_cell, room_polygon=room.polygon,
            c0_offset_deg=C0_ORIENTATION_OFFSET_DEG,
        )
        for fixture in fixtures
    }
    raw_wall_direct: dict[str, dict[str, Matrix]] = {}
    for wall in room.walls:
        patches = wall_patches[wall.id]
        if not patches:
            raw_wall_direct[wall.id] = {}
            continue
        cell = patches[0].size
        per_fix: dict[str, Matrix] = {}
        for fixture in fixtures:
            m = compute_direct_matrix(
                fixture, patches, "wall", patch_size=cell, wall_id=wall.id,
                room_polygon=room.polygon, c0_offset_deg=C0_ORIENTATION_OFFSET_DEG,
            )
            m = Matrix(m.values, {**m.metadata, "patchSize": cell, "wallId": wall.id})
            per_fix[fixture.id] = m
        raw_wall_direct[wall.id] = per_fix
    ceiling_cell = ceiling_patches[0].size if ceiling_patches else floor_cell
    raw_ceiling_direct = {
        fixture.id: compute_direct_matrix(
            fixture, ceiling_patches, "ceiling", patch_size=ceiling_cell, room_polygon=room.polygon,
            c0_offset_deg=C0_ORIENTATION_OFFSET_DEG,
        )
        for fixture in fixtures
    } if ceiling_patches else {}

    all_wall_patches: list[Patch] = [p for wall in room.walls for p in wall_patches[wall.id]]
    all_source_patches: list[Patch] = [*all_wall_patches, *floor_patches, *ceiling_patches]
    offsets: dict[str, int] = {}
    pos = 0
    for wall in room.walls:
        offsets[wall.id] = pos
        pos += len(wall_patches[wall.id])
    floor_offset = pos
    pos += len(floor_patches)
    ceiling_offset = pos

    seeds: dict[str, list[float]] = {}
    if fixtures:
        for wall in room.walls:
            per_fix = raw_wall_direct.get(wall.id, {})
            if not per_fix or not wall_patches[wall.id]:
                continue
            total_wall = sum_matrices(list(per_fix.values()))
            seed = [0.0] * len(all_source_patches)
            start = offsets[wall.id]
            seed[start:start + len(total_wall.values)] = list(total_wall.values)
            seeds[wall.id] = seed
        if raw_floor_direct:
            total_floor_direct = sum_matrices(list(raw_floor_direct.values()))
            seed = [0.0] * len(all_source_patches)
            seed[floor_offset:floor_offset + len(total_floor_direct.values)] = list(total_floor_direct.values)
            seeds["floor"] = seed
        if raw_ceiling_direct and ceiling_patches:
            total_ceiling_direct = sum_matrices(list(raw_ceiling_direct.values()))
            seed = [0.0] * len(all_source_patches)
            seed[ceiling_offset:ceiling_offset + len(total_ceiling_direct.values)] = list(total_ceiling_direct.values)
            seeds["ceiling"] = seed

    targets: dict[str, list[Patch]] = {"floor": floor_patches, "ceiling": ceiling_patches}
    for wall in room.walls:
        targets[wall.id] = wall_patches[wall.id]

    mf = MAINTENANCE_FACTOR
    applied_bounces = NUM_BOUNCES if fixtures and NUM_BOUNCES > 0 and seeds else 0
    if seeds and applied_bounces > 0:
        per_target = compute_indirect_per_target_per_origin(
            all_source_patches, seeds, targets,
            WALL_REFLECTANCE_FACTOR, applied_bounces, room.polygon,
            floor_reflectance=FLOOR_REFLECTANCE_FACTOR,
            ceiling_reflectance=CEILING_REFLECTANCE_FACTOR,
        )
    else:
        per_target = {tid: {oid: [0.0] * len(tp) for oid in seeds} for tid, tp in targets.items()}
        if not seeds:
            per_target = {tid: {} for tid in targets}

    def _indirect_matrices(tid: str, tgt: list[Patch], cell: float) -> dict[str, Matrix]:
        out: dict[str, Matrix] = {}
        per_origin = per_target.get(tid, {})
        for oid, vals in per_origin.items():
            out[oid] = Matrix(list(vals), {
                "kind": "indirect", "surfaceType": "floor" if tid == "floor" else ("ceiling" if tid == "ceiling" else "wall"),
                "targetId": tid, "sourceWallId": oid, "patchSize": cell, "bounces": applied_bounces,
                "wallReflectance": WALL_REFLECTANCE_FACTOR, "floorReflectance": FLOOR_REFLECTANCE_FACTOR,
                "ceilingReflectance": CEILING_REFLECTANCE_FACTOR,
            })
        return out

    raw_indirect_floor = _indirect_matrices("floor", floor_patches, floor_cell)
    raw_indirect_ceiling = _indirect_matrices("ceiling", ceiling_patches, ceiling_cell)
    raw_indirect_walls: dict[str, dict[str, Matrix]] = {}
    for wall in room.walls:
        patches = wall_patches[wall.id]
        cell = patches[0].size if patches else 0.0
        raw_indirect_walls[wall.id] = _indirect_matrices(wall.id, patches, cell)

    raw_total_floor = sum_matrices([*raw_floor_direct.values(), *raw_indirect_floor.values()]) if (raw_floor_direct or raw_indirect_floor) else Matrix([0.0] * len(floor_patches), {"kind": "raw-total"})
    total_floor = apply_maintenance_factor(raw_total_floor, mf)
    if ceiling_patches:
        raw_total_ceiling = sum_matrices([*raw_ceiling_direct.values(), *raw_indirect_ceiling.values()]) if (raw_ceiling_direct or raw_indirect_ceiling) else Matrix([0.0] * len(ceiling_patches), {"kind": "raw-total"})
        total_ceiling = apply_maintenance_factor(raw_total_ceiling, mf)
    else:
        total_ceiling = Matrix([], {"kind": "total", "surfaceType": "ceiling"})
    total_walls: dict[str, Matrix] = {}
    for wall in room.walls:
        patches = wall_patches[wall.id]
        if not patches:
            total_walls[wall.id] = Matrix([], {"kind": "total", "surfaceType": "wall"})
            continue
        parts = [*raw_wall_direct.get(wall.id, {}).values(), *raw_indirect_walls.get(wall.id, {}).values()]
        raw_total = sum_matrices(parts) if parts else Matrix([0.0] * len(patches), {"kind": "raw-total"})
        total_walls[wall.id] = apply_maintenance_factor(raw_total, mf)

    evaluation = _evaluation(floor_patches, total_floor.values, grid_meta, work_z, floor_border)
    ceiling_evaluation = _evaluation(ceiling_patches, total_ceiling.values, ceiling_meta, ceiling_h, ceiling_border) if ceiling_patches and total_ceiling.values else None
    wall_evaluations = {}
    for wall in room.walls:
        patches = wall_patches[wall.id]
        vals = total_walls[wall.id].values
        if patches and vals:
            wall_evaluations[wall.id] = _evaluation(patches, vals, wall_metas[wall.id], wall.height, wall_metas[wall.id].get("border", 0.0))
    response = CalculateResponse(
        fixtures=[_fixture(fixture) for fixture in fixtures],
        floorPatches=[_patch(p) for p in floor_patches],
        wallPatches={wid: [_patch(p) for p in pts] for wid, pts in wall_patches.items()},
        ceilingPatches=[_patch(p) for p in ceiling_patches],
        directFloorMatrices={fid: _matrix(apply_maintenance_factor(m, mf)) for fid, m in raw_floor_direct.items()},
        directWallMatrices={
            wid: {fid: _matrix(apply_maintenance_factor(m, mf)) for fid, m in per_fix.items()}
            for wid, per_fix in raw_wall_direct.items()
        },
        directCeilingMatrices={fid: _matrix(apply_maintenance_factor(m, mf)) for fid, m in raw_ceiling_direct.items()},
        indirectFloorMatrices={wid: _matrix(apply_maintenance_factor(m, mf)) for wid, m in raw_indirect_floor.items()},
        indirectCeilingMatrices={wid: _matrix(apply_maintenance_factor(m, mf)) for wid, m in raw_indirect_ceiling.items()},
        indirectWallMatrices={
            wid: {oid: _matrix(apply_maintenance_factor(m, mf)) for oid, m in per_origin.items()}
            for wid, per_origin in raw_indirect_walls.items()
        },
        totalFloorIlluminance=_matrix(total_floor),
        totalCeilingIlluminance=_matrix(total_ceiling),
        totalWallIlluminance={wid: _matrix(m) for wid, m in total_walls.items()},
        evaluation=evaluation,
        ceilingEvaluation=ceiling_evaluation,
        wallEvaluations=wall_evaluations,
        bounces=applied_bounces,
        wallReflectance=WALL_REFLECTANCE_FACTOR,
        floorReflectance=FLOOR_REFLECTANCE_FACTOR,
        ceilingReflectance=CEILING_REFLECTANCE_FACTOR,
        ceilingHeight=ceiling_h,
        mountingHeight=mount_h,
    )
    _log.info(
        "success duration_ms=%.1f bounces=%s wall_reflectance=%s floor_reflectance=%s ceiling_reflectance=%s",
        (time.perf_counter() - started) * 1000,
        applied_bounces,
        WALL_REFLECTANCE_FACTOR,
        FLOOR_REFLECTANCE_FACTOR,
        CEILING_REFLECTANCE_FACTOR,
    )
    return response


def _vec(v: Vec3) -> Vec3Dto:
    return Vec3Dto(x=v[0], y=v[1], z=v[2])


def _fixture(fixture: Fixture) -> FixtureDto:
    corners, elements = luminous_opening(fixture)
    return FixtureDto(
        id=fixture.id,
        position=_vec(fixture.position),
        aimDirection=_vec(fixture.aim_direction),
        rotation=fixture.rotation,
        length=fixture.ies_profile.length,
        width=fixture.ies_profile.width,
        height=fixture.ies_profile.height,
        corners=[_vec(c) for c in corners],
        elements=[_vec(e) for e in elements],
    )


def _patch(patch: Patch) -> PatchDto:
    return PatchDto(
        id=patch.id,
        surfaceType=patch.surface_type,
        parentId=patch.parent_id,
        center=Vec3Dto(x=patch.center[0], y=patch.center[1], z=patch.center[2]),
        normal=Vec3Dto(x=patch.normal[0], y=patch.normal[1], z=patch.normal[2]),
        area=patch.area,
        size=patch.size,
    )


def _matrix(matrix: Matrix) -> MatrixDto:
    return MatrixDto(values=matrix.values, metadata=matrix.metadata)


def _evaluation(
    patches: list[Patch],
    total_values: list[float],
    grid_meta: dict[str, float],
    ref_z: float,
    wall_zone: float,
) -> EvaluationDto:
    lo = min(total_values)
    hi = max(total_values)
    avg = sum(total_values) / len(total_values)
    i_min = total_values.index(lo)
    i_max = total_values.index(hi)
    return EvaluationDto(
        average=avg,
        minimum=lo,
        maximum=hi,
        uniformity=(lo / avg if avg > 0 else 0.0),
        minPoint=_vec(patches[i_min].center),
        maxPoint=_vec(patches[i_max].center),
        count=len(patches),
        spacing=float(grid_meta.get("spacing", 0.0)),
        spacingX=float(grid_meta.get("spacingX", grid_meta.get("spacing", 0.0))),
        spacingY=float(grid_meta.get("spacingY", grid_meta.get("spacing", 0.0))),
        nx=int(grid_meta.get("nx", 0)),
        ny=int(grid_meta.get("ny", 0)),
        wallZone=wall_zone,
        workPlaneHeight=ref_z,
    )
