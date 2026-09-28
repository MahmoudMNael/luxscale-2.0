"""HTTP-adjacent adapter: schemas <-> engine. Physics lives in app.engine."""

from __future__ import annotations

from itertools import product
import math

from app.app_settings import (
    CEILING_REFLECTANCE_FACTOR,
    FLOOR_REFLECTANCE_FACTOR,
    MAINTENANCE_FACTOR,
    NUM_BOUNCES,
    WALL_REFLECTANCE_FACTOR,
)
from app.domain.models import Fixture, FixturePlacement, IESProfile, Matrix, Patch, Vec3
from app.engine import (
    EngineInput,
    EngineResult,
    EvalGrids,
    EvalSummary,
    PhysicsOptions,
    RoomInput,
    SolverCache,
    build_eval_grids,
    build_room,
    build_solver_cache,
    resolve_fixtures,
    run,
)
from app.engine import calculate as engine_calculate
from app.providers import FixtureSpec, StandardTarget
from app.schemas.calculate import (
    CalculateRequest,
    CalculateResponse,
    ComplianceResultDto,
    ComplianceTargetInput,
    EvaluationDto,
    FixtureDto,
    VariantResultDto,
)
from app.schemas.geometry import PatchDto, Vec3Dto
from app.schemas.grid import GridInput
from app.schemas.matrix import MatrixDto
from app.services._luxcore_bridge import IesHandleCache
from app.services.fixture_service import axis_positions, luminous_opening
from app.services.ies_service import load_ies
from app.services.variant_photometrics import apply_variant_dimensions, scale_profile_to_lumens
from app.services.vector_math import EPS, point_in_polygon, polygon_area


def calculate(payload: CalculateRequest, ies_text: str) -> CalculateResponse:
    """Legacy single-profile entry point (grid or shared-IES placements)."""
    return calculate_extended(payload, profiles={"default": load_ies(ies_text)}, default_ref="default")


def calculate_with_profiles(
    payload: CalculateRequest,
    profiles: dict[str, IESProfile],
    default_ref: str | None = None,
    standard_target: StandardTarget | None = None,
) -> CalculateResponse:
    """Heterogeneous entry point: per-fixture ies_ref keys into profiles."""
    return calculate_extended(
        payload=payload,
        profiles=profiles,
        default_ref=default_ref,
        standard_target=standard_target,
    )


def calculate_extended(
    payload: CalculateRequest,
    profiles: dict[str, IESProfile] | None = None,
    variant_specs: list[FixtureSpec] | None = None,
    specs_by_id: dict[str, FixtureSpec] | None = None,
    default_ref: str | None = None,
    standard_target: StandardTarget | None = None,
) -> CalculateResponse:
    """Unified advanced entry point: handles heterogeneous fixtures, flexible grids, tilt, and compliance."""
    IesHandleCache.clear()
    polygon = [(p.x, p.y) for p in payload.polygon]
    room_in = RoomInput(
        polygon=polygon,
        ceiling_height=payload.ceilingHeight,
        mounting_height=payload.mountingHeight,
        work_plane_height=payload.workPlaneHeight,
        floor_zone=payload.floorZone,
        wall_zone=payload.wallZone,
    )
    room, ceiling_h, mount_h, work_z = build_room(room_in)
    eval_grids = build_eval_grids(room, work_z, payload.floorZone, payload.wallZone)

    options = _physics_options(payload)
    solver_cache = build_solver_cache(room, eval_grids, ceiling_h, options)

    if payload.grid is not None:
        placements = _grid_placements(
            polygon,
            payload.grid,
            payload.luminaireRotation,
            default_variant_id=payload.variantId,
            default_ref=default_ref,
        )
    else:
        placements = _free_placements(
            payload.fixtures or [],
            payload.luminaireRotation,
            default_variant_id=payload.variantId,
            default_ref=default_ref,
        )

    area = polygon_area(polygon)
    active_profiles = profiles or {}
    d_ref = default_ref or payload.variantId or (next(iter(active_profiles)) if len(active_profiles) == 1 else None)
    engine_fixtures = resolve_fixtures(room, placements, active_profiles, mount_h, default_ref=d_ref)
    res = run(engine_fixtures, room, eval_grids, solver_cache, options)
    comp = _check_compliance(res.evaluation, payload.compliance, standard_target)

    # Compute wattage across placed fixtures
    specs = dict(specs_by_id or {})
    if variant_specs:
        for s in variant_specs:
            specs[s.id] = s

    total_watts: float = 0.0
    has_wattage = False
    for fix in engine_fixtures:
        v_key = fix.variant_id or fix.ies_ref
        spec = specs.get(v_key or "")
        if spec and spec.wattage is not None:
            total_watts += float(spec.wattage)
            has_wattage = True

    pw = total_watts if has_wattage else None
    pd = (pw / area) if pw is not None and area > 0 else None

    v_dto = _to_variant_result(
        res,
        eval_grids,
        variant_id=payload.variantId or d_ref,
        compliance=comp,
        power_w=pw,
        power_density=pd,
        include_details=payload.includeWallCeilingMatrices,
    )
    variant_results = [v_dto]

    primary = variant_results[0]
    first_fixtures = primary.fixtures
    first_eval = primary.evaluation
    first_total_floor = primary.totalFloorIlluminance

    return CalculateResponse(
        fixtures=first_fixtures,
        floorPatches=[_patch(p) for p in eval_grids.floor],
        wallPatches={wid: [_patch(p) for p in pts] for wid, pts in eval_grids.walls.items()},
        ceilingPatches=[_patch(p) for p in eval_grids.ceiling],
        directFloorMatrices=primary.directFloorMatrices,
        directWallMatrices=primary.directWallMatrices,
        directCeilingMatrices=primary.directCeilingMatrices,
        indirectFloorMatrices=primary.indirectFloorMatrices,
        indirectCeilingMatrices=primary.indirectCeilingMatrices,
        indirectWallMatrices=primary.indirectWallMatrices,
        totalFloorIlluminance=first_total_floor,
        totalCeilingIlluminance=primary.totalCeilingIlluminance,
        totalWallIlluminance=primary.totalWallIlluminance,
        evaluation=first_eval,
        ceilingEvaluation=primary.ceilingEvaluation,
        wallEvaluations=primary.wallEvaluations,
        bounces=options.bounces,
        wallReflectance=options.wall_reflectance,
        floorReflectance=options.floor_reflectance,
        ceilingReflectance=options.ceiling_reflectance,
        maintenanceFactor=options.maintenance_factor,
        ceilingHeight=ceiling_h,
        mountingHeight=mount_h,
        solverCell=solver_cache.cell,
        solverDegraded=solver_cache.degraded,
        compliance=primary.compliance,
        powerW=pw,
        powerDensity=pd,
        results=variant_results,
    )


def _physics_options(payload: CalculateRequest) -> PhysicsOptions:
    return PhysicsOptions(
        wall_reflectance=payload.wallReflectance or WALL_REFLECTANCE_FACTOR,
        floor_reflectance=payload.floorReflectance or FLOOR_REFLECTANCE_FACTOR,
        ceiling_reflectance=payload.ceilingReflectance or CEILING_REFLECTANCE_FACTOR,
        maintenance_factor=payload.maintenanceFactor or MAINTENANCE_FACTOR,
        bounces=payload.bounces if payload.bounces is not None else NUM_BOUNCES,
    )


def _check_compliance(
    summary: EvalSummary,
    payload_compliance: ComplianceTargetInput | None,
    standard_target: StandardTarget | None,
) -> ComplianceResultDto | None:
    target_lux = None
    target_uo = None
    max_over = 0.3
    if standard_target is not None:
        target_lux = standard_target.avg_lux
        target_uo = standard_target.uniformity
        max_over = standard_target.max_overdesign
    elif payload_compliance is not None:
        target_lux = payload_compliance.targetLux
        target_uo = payload_compliance.targetUniformity
        max_over = payload_compliance.maxOverdesign
    if target_lux is None or target_uo is None:
        return None
    avg = summary.average
    uo = summary.uniformity
    compliant = bool(avg >= target_lux and uo >= target_uo and avg <= target_lux * (1.0 + max_over))
    return ComplianceResultDto(
        compliant=compliant,
        targetLux=float(target_lux),
        targetUniformity=float(target_uo),
        luxGap=round(float(avg - target_lux), 2),
        uniformityGap=round(float(uo - target_uo), 3),
        overdesign=round(float((avg / target_lux) - 1.0), 3),
    )


def _count_axis(min_v: float, width: float, n: int, frac: float) -> list[float]:
    if n <= 1:
        return [min_v + width / 2.0]
    denom = n - 1.0 + 2.0 * frac
    s = width / denom if denom > EPS else width
    return [min_v + s * frac + i * s for i in range(n)]


def _spacing_axis(min_v: float, width: float, spacing: float) -> list[float]:
    n = max(1, int(round(width / spacing))) if spacing > EPS else 1
    off = (width - (n - 1) * spacing) / 2.0
    return [min_v + off + i * spacing for i in range(n)]


def _stepped_axis(min_v: float, max_v: float, spacing: float, offset: float) -> list[float]:
    pts: list[float] = []
    cur = min_v + offset
    while cur <= max_v - offset + EPS:
        pts.append(cur)
        cur += spacing
    return pts


def _grid_placements(
    polygon: list[tuple[float, float]],
    grid: GridInput,
    rotation: float,
    default_variant_id: str | None = None,
    default_ref: str | None = None,
) -> list[FixturePlacement]:
    """Generates fixture placements from count-based, spacing-based, or axis-based GridInput."""
    xs = [p[0] for p in polygon]
    ys = [p[1] for p in polygon]
    xmin, xmax, ymin, ymax = min(xs), max(xs), min(ys), max(ys)
    wx, wy = xmax - xmin, ymax - ymin

    if grid.count is not None:
        x_pts = _count_axis(xmin, wx, max(1, grid.count.count_x), grid.count.offset_fraction)
        y_pts = _count_axis(ymin, wy, max(1, grid.count.count_y), grid.count.offset_fraction)
    elif grid.spacing is not None:
        if grid.spacing.auto_center:
            x_pts = _spacing_axis(xmin, wx, grid.spacing.spacing_x)
            y_pts = _spacing_axis(ymin, wy, grid.spacing.spacing_y)
        else:
            x_pts = _stepped_axis(xmin, xmax, grid.spacing.spacing_x, grid.spacing.offset_x or 0.0)
            y_pts = _stepped_axis(ymin, ymax, grid.spacing.spacing_y, grid.spacing.offset_y or 0.0)
    elif grid.x is not None and grid.y is not None:
        x_pts = axis_positions(xmin, xmax, grid.x.spacing, grid.x.offset_beginning, grid.x.offset_ending)
        y_pts = axis_positions(ymin, ymax, grid.y.spacing, grid.y.offset_beginning, grid.y.offset_ending)
    else:
        return []

    return [
        FixturePlacement(
            id=f"F{i + 1}",
            x=x,
            y=y,
            rotation=rotation,
            ies_ref=default_ref,
            variant_id=default_variant_id,
        )
        for i, (y, x) in enumerate(
            (y, x) for y, x in product(y_pts, x_pts) if point_in_polygon((x, y), polygon)
        )
    ]


def _free_placements(
    fixtures_dto: list,
    luminaire_rotation: float,
    default_variant_id: str | None = None,
    default_ref: str | None = None,
) -> list[FixturePlacement]:
    """Translates FixturePlacementDto models to engine FixturePlacement instances with tilt support."""
    placements: list[FixturePlacement] = []
    for i, f in enumerate(fixtures_dto):
        rot = f.rotation if f.rotation is not None else luminaire_rotation
        if f.aimDirection is not None:
            aim = (f.aimDirection.x, f.aimDirection.y, f.aimDirection.z)
        elif f.tiltAngle and f.tiltAngle > 0:
            tilt_rad = math.radians(f.tiltAngle)
            rot_rad = math.radians(rot)
            aim = (
                math.sin(tilt_rad) * math.cos(rot_rad),
                math.sin(tilt_rad) * math.sin(rot_rad),
                -math.cos(tilt_rad),
            )
        else:
            aim = (0.0, 0.0, -1.0)

        v_id = f.variantId or default_variant_id
        i_ref = f.iesRef or (default_ref if not f.variantId else None)

        placements.append(
            FixturePlacement(
                id=f.id or f"F{i + 1}",
                x=f.x,
                y=f.y,
                z=f.z,
                rotation=rot,
                aim_direction=aim,
                ies_ref=i_ref,
                variant_id=v_id,
                tilt_angle=f.tiltAngle or 0.0,
            )
        )
    return placements


def _to_variant_result(
    result: EngineResult,
    ev: EvalGrids,
    variant_id: str | None,
    compliance: ComplianceResultDto | None,
    power_w: float | None,
    power_density: float | None,
    include_details: bool,
) -> VariantResultDto:
    eval_dto = _evaluation(ev.floor, result.evaluation, ev.floor_meta, ev.work_z, ev.floor_border)
    tot_floor = _matrix(result.total_floor)
    fixtures_dto = [_fixture(f) for f in result.fixtures]

    if not include_details:
        return VariantResultDto(
            variantId=variant_id,
            evaluation=eval_dto,
            totalFloorIlluminance=tot_floor,
            compliance=compliance,
            powerW=power_w,
            powerDensity=power_density,
            fixtures=fixtures_dto,
        )

    wall_evals = {
        wid: _evaluation(
            ev.walls[wid], summary, ev.wall_metas[wid],
            result.ceiling_height, ev.wall_metas[wid].get("border", 0.0),
        )
        for wid, summary in result.wall_evaluations.items()
    }
    ceil_eval = (
        _evaluation(
            ev.ceiling, result.ceiling_evaluation, ev.ceiling_meta,
            result.ceiling_height, ev.ceiling_border,
        )
        if result.ceiling_evaluation is not None
        else None
    )

    return VariantResultDto(
        variantId=variant_id,
        evaluation=eval_dto,
        totalFloorIlluminance=tot_floor,
        compliance=compliance,
        powerW=power_w,
        powerDensity=power_density,
        fixtures=fixtures_dto,
        wallEvaluations=wall_evals,
        ceilingEvaluation=ceil_eval,
        totalWallIlluminance={wid: _matrix(m) for wid, m in result.total_walls.items()},
        totalCeilingIlluminance=_matrix(result.total_ceiling) if result.total_ceiling else None,
        directFloorMatrices={fid: _matrix(m) for fid, m in result.direct_floor.items()},
        indirectFloorMatrices={oid: _matrix(m) for oid, m in result.indirect_floor.items()},
        directWallMatrices={
            wid: {fid: _matrix(m) for fid, m in per_fix.items()}
            for wid, per_fix in result.direct_walls.items()
        },
        indirectWallMatrices={
            wid: {oid: _matrix(m) for oid, m in per_origin.items()}
            for wid, per_origin in result.indirect_walls.items()
        },
        directCeilingMatrices={fid: _matrix(m) for fid, m in result.direct_ceiling.items()},
        indirectCeilingMatrices={oid: _matrix(m) for oid, m in result.indirect_ceiling.items()},
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
        variantId=fixture.variant_id,
        iesRef=fixture.ies_ref,
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
