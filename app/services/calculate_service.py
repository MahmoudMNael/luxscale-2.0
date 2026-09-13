from __future__ import annotations

import logging
import time

from app.app_settings import FLOOR_BORDER, MAINTENANCE_FACTOR, PATCH_SIZE, REFLECTANCE_FACTOR, WORK_PLANE_HEIGHT
from app.domain.exceptions import GeometryError
from app.domain.models import Fixture, FloorSurface, Matrix, Patch, Vec3, WallSurface
from app.schemas.calculate import CalculateRequest, CalculateResponse, FixtureDto
from app.schemas.geometry import PatchDto, Vec3Dto
from app.schemas.matrix import MatrixDto
from app.services.direct_illuminance_service import compute_direct_matrix
from app.services.fixture_service import generate_fixture_grid, luminous_opening
from app.services.geometry_service import define_room, generate_patches
from app.services.ies_service import load_ies
from app.services.indirect_illuminance_service import compute_indirect_matrix_from_wall
from app.services.matrix_service import apply_maintenance_factor, sum_matrices

_log = logging.getLogger(__name__)


def calculate(payload: CalculateRequest, ies_text: str) -> CalculateResponse:
    started = time.perf_counter()
    _log.info(
        "start vertices=%s height=%s spacing=(%s,%s) offsets_x=(%s,%s) offsets_y=(%s,%s)",
        len(payload.polygon),
        payload.height,
        payload.grid.x.spacing,
        payload.grid.y.spacing,
        payload.grid.x.offset_beginning,
        payload.grid.x.offset_ending,
        payload.grid.y.offset_beginning,
        payload.grid.y.offset_ending,
    )
    room = define_room([(p.x, p.y) for p in payload.polygon], payload.height, step=PATCH_SIZE)
    floor_patches = generate_patches(
        FloorSurface(room.polygon),
        plane_z=WORK_PLANE_HEIGHT,
        border=FLOOR_BORDER,
    )
    if not floor_patches:
        raise GeometryError("No floor patches remain after clipping to the polygon.")
    wall_patches = {
        wall.id: generate_patches(
            WallSurface(wall.id, wall.start, wall.end, wall.height, wall.normal),
            PATCH_SIZE,
            plane_z=WORK_PLANE_HEIGHT,
        )
        for wall in room.walls
    }
    floor_cell = floor_patches[0].size
    _log.info(
        "geometry walls=%s floor_patches=%s wall_patches=%s",
        len(room.walls),
        len(floor_patches),
        {wid: len(pts) for wid, pts in wall_patches.items()},
    )
    ies = load_ies(ies_text)
    fixtures = generate_fixture_grid(room, payload.grid, room.height, ies)
    _log.info("fixtures=%s", len(fixtures))

    raw_floor_direct = {
        fixture.id: compute_direct_matrix(fixture, floor_patches, "floor", patch_size=floor_cell)
        for fixture in fixtures
    }
    raw_wall_direct: dict[str, dict[str, Matrix]] = {wall.id: {} for wall in room.walls}
    for wall in room.walls:
        for fixture in fixtures:
            raw_wall_direct[wall.id][fixture.id] = compute_direct_matrix(
                fixture,
                wall_patches[wall.id],
                "wall",
                patch_size=PATCH_SIZE,
                wall_id=wall.id,
            )

    raw_indirect: dict[str, Matrix] = {}
    for wall in room.walls:
        total_wall = sum_matrices(list(raw_wall_direct[wall.id].values()))
        raw_indirect[wall.id] = compute_indirect_matrix_from_wall(
            wall_patches[wall.id],
            total_wall,
            floor_patches,
            REFLECTANCE_FACTOR,
            source_wall_id=wall.id,
            patch_size=floor_cell,
        )

    raw_total = sum_matrices([*raw_floor_direct.values(), *raw_indirect.values()])
    mf = MAINTENANCE_FACTOR
    response = CalculateResponse(
        fixtures=[_fixture(fixture) for fixture in fixtures],
        floorPatches=[_patch(p) for p in floor_patches],
        wallPatches={wid: [_patch(p) for p in pts] for wid, pts in wall_patches.items()},
        directFloorMatrices={fid: _matrix(apply_maintenance_factor(m, mf)) for fid, m in raw_floor_direct.items()},
        directWallMatrices={
            wid: {fid: _matrix(apply_maintenance_factor(m, mf)) for fid, m in per_fix.items()}
            for wid, per_fix in raw_wall_direct.items()
        },
        indirectFloorMatrices={wid: _matrix(apply_maintenance_factor(m, mf)) for wid, m in raw_indirect.items()},
        totalFloorIlluminance=_matrix(apply_maintenance_factor(raw_total, mf)),
    )
    _log.info("success duration_ms=%.1f", (time.perf_counter() - started) * 1000)
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
