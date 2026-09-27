"""HTTP-adjacent adapter: schemas <-> engine. Physics lives in app.engine."""

from __future__ import annotations

from app.domain.models import Fixture, FixturePlacement, IESProfile, Matrix, Patch, Vec3
from app.engine import EngineInput, EngineResult, EvalSummary, RoomInput
from app.engine import calculate as engine_calculate
from app.schemas.calculate import CalculateRequest, CalculateResponse, EvaluationDto, FixtureDto
from app.schemas.geometry import PatchDto, Vec3Dto
from app.schemas.matrix import MatrixDto
from app.services.fixture_service import axis_positions, luminous_opening
from app.services.ies_service import load_ies
from app.services.vector_math import point_in_polygon


def calculate(payload: CalculateRequest, ies_text: str) -> CalculateResponse:
    """Legacy single-profile entry point (grid or shared-IES placements)."""
    profile = load_ies(ies_text)
    return calculate_with_profiles(payload, {"default": profile}, default_ref="default")


def calculate_with_profiles(
    payload: CalculateRequest,
    profiles: dict[str, IESProfile],
    default_ref: str | None = None,
) -> CalculateResponse:
    """Heterogeneous entry point: per-fixture ies_ref keys into profiles."""
    polygon = [(p.x, p.y) for p in payload.polygon]
    if payload.grid is not None:
        placements = _grid_placements(polygon, payload.grid, payload.luminaireRotation)
    else:
        placements = [
            FixturePlacement(
                id=f.id or f"F{i + 1}",
                x=f.x,
                y=f.y,
                z=f.z,
                rotation=f.rotation if f.rotation is not None else payload.luminaireRotation,
                aim_direction=(
                    (f.aimDirection.x, f.aimDirection.y, f.aimDirection.z)
                    if f.aimDirection is not None
                    else (0.0, 0.0, -1.0)
                ),
                ies_ref=f.iesRef,
            )
            for i, f in enumerate(payload.fixtures or [])
        ]
    result = engine_calculate(
        EngineInput(
            room=RoomInput(
                polygon=polygon,
                ceiling_height=(
                    payload.ceilingHeight if payload.ceilingHeight is not None else payload.height
                ),
                mounting_height=payload.mountingHeight,
                work_plane_height=payload.workPlaneHeight,
                floor_zone=payload.floorZone,
                wall_zone=payload.wallZone,
            ),
            placements=placements,
        ),
        profiles,
        default_ref=default_ref,
    )
    return _to_response(result)


def _grid_placements(polygon: list[tuple[float, float]], grid, rotation: float) -> list[FixturePlacement]:
    """Legacy GridInput -> free placements (same positions/ids as before)."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    placements: list[FixturePlacement] = []
    n = 1
    for y in axis_positions(ymin, ymax, grid.y.spacing, grid.y.offset_beginning, grid.y.offset_ending):
        for x in axis_positions(xmin, xmax, grid.x.spacing, grid.x.offset_beginning, grid.x.offset_ending):
            if not point_in_polygon((x, y), polygon):
                continue
            placements.append(FixturePlacement(id=f"F{n}", x=x, y=y, rotation=rotation))
            n += 1
    return placements


def _to_response(result: EngineResult) -> CalculateResponse:
    ev = result.eval
    return CalculateResponse(
        fixtures=[_fixture(f) for f in result.fixtures],
        floorPatches=[_patch(p) for p in ev.floor],
        wallPatches={wid: [_patch(p) for p in pts] for wid, pts in ev.walls.items()},
        ceilingPatches=[_patch(p) for p in ev.ceiling],
        directFloorMatrices={fid: _matrix(m) for fid, m in result.direct_floor.items()},
        directWallMatrices={
            wid: {fid: _matrix(m) for fid, m in per_fix.items()}
            for wid, per_fix in result.direct_walls.items()
        },
        directCeilingMatrices={fid: _matrix(m) for fid, m in result.direct_ceiling.items()},
        indirectFloorMatrices={oid: _matrix(m) for oid, m in result.indirect_floor.items()},
        indirectCeilingMatrices={
            oid: _matrix(m) for oid, m in result.indirect_ceiling.items()
        },
        indirectWallMatrices={
            wid: {oid: _matrix(m) for oid, m in per_origin.items()}
            for wid, per_origin in result.indirect_walls.items()
        },
        totalFloorIlluminance=_matrix(result.total_floor),
        totalCeilingIlluminance=_matrix(result.total_ceiling),
        totalWallIlluminance={wid: _matrix(m) for wid, m in result.total_walls.items()},
        evaluation=_evaluation(ev.floor, result.evaluation, ev.floor_meta, ev.work_z, ev.floor_border),
        ceilingEvaluation=(
            _evaluation(
                ev.ceiling, result.ceiling_evaluation, ev.ceiling_meta,
                result.ceiling_height, ev.ceiling_border,
            )
            if result.ceiling_evaluation is not None
            else None
        ),
        wallEvaluations={
            wid: _evaluation(
                ev.walls[wid], summary, ev.wall_metas[wid],
                result.ceiling_height, ev.wall_metas[wid].get("border", 0.0),
            )
            for wid, summary in result.wall_evaluations.items()
        },
        bounces=result.bounces,
        wallReflectance=result.options.wall_reflectance,
        floorReflectance=result.options.floor_reflectance,
        ceilingReflectance=result.options.ceiling_reflectance,
        ceilingHeight=result.ceiling_height,
        mountingHeight=result.mounting_height,
        solverCell=result.solver_cell,
        solverDegraded=result.solver_degraded,
    )


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
    summary: EvalSummary,
    grid_meta: dict[str, float],
    ref_z: float,
    wall_zone: float,
) -> EvaluationDto:
    return EvaluationDto(
        average=summary.average,
        minimum=summary.minimum,
        maximum=summary.maximum,
        uniformity=summary.uniformity,
        minPoint=_vec(patches[summary.min_index].center),
        maxPoint=_vec(patches[summary.max_index].center),
        count=summary.count,
        spacing=float(grid_meta.get("spacing", 0.0)),
        spacingX=float(grid_meta.get("spacingX", grid_meta.get("spacing", 0.0))),
        spacingY=float(grid_meta.get("spacingY", grid_meta.get("spacing", 0.0))),
        nx=int(grid_meta.get("nx", 0)),
        ny=int(grid_meta.get("ny", 0)),
        wallZone=wall_zone,
        workPlaneHeight=ref_z,
    )
