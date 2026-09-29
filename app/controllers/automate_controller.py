from __future__ import annotations

from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.exceptions import RequestValidationError

from app.app_settings import (
    CEILING_REFLECTANCE_FACTOR,
    FLOOR_REFLECTANCE_FACTOR,
    WALL_REFLECTANCE_FACTOR,
)
from app.automate import Solution, frange
from app.automate import automate as run_search
from app.automate.layouts import auto_spacing_range
from app.engine import PhysicsOptions, RoomInput
from app.providers import (
    FixtureProvider,
    RestFixtureProvider,
    RestStandardProvider,
    StandardProvider,
    StandardTarget,
)
from app.schemas.automate import (
    AppliedSpacingDto,
    AutomateFixtureDto,
    AutomatePlacementDto,
    AutomateRequest,
    AutomateResponse,
    GridHintDto,
    SolutionDto,
    SpacingRange,
    TargetDto,
    _MAX_CANDIDATES,
    candidate_count,
)
from app.schemas.errors import ErrorResponse
from app.schemas.geometry import PatchDto, Vec3Dto
from app.schemas.matrix import MatrixDto
from app.services.ies_service import load_ies
from app.services.variant_photometrics import apply_variant_dimensions, scale_profile_to_lumens
from app.services.vector_math import polygon_area

router = APIRouter()


def _standard_provider() -> StandardProvider:
    return RestStandardProvider()


def _fixture_provider() -> FixtureProvider:
    return RestFixtureProvider()


@router.post(
    "/automate",
    response_model=AutomateResponse,
    responses={
        400: {"model": ErrorResponse, "description": "IES, geometry or provider error"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def automate(
    payload: AutomateRequest,
    standards: Annotated[StandardProvider, Depends(_standard_provider)] = None,  # type: ignore[assignment]
    fixtures: Annotated[FixtureProvider, Depends(_fixture_provider)] = None,  # type: ignore[assignment]
) -> AutomateResponse:
    """Variant-driven automate search (JSON body, no file uploads).

    - Target from `GET {STANDARDS_BASE_URL}/api/v1/standards/{activityId}`
      (avg/uniformity); overdesign cap from `maxOverdesign` when given,
      else the standard default.
    - Application from mounting height: <= 3.0 -> interior else industrial
      (see `application_for_mounting_height` in schemas/automate.py).
    - Variants: explicit `variantIds` or all main-solution variants for the
      application (`is_main_solution=true` filter, provider-side).
    - IES shape from each variant's `ies_file_id` asset bytes; watts/lumens
      from `variant.power`/`variant.efficacy` via variant_photometrics.
    """
    providers_std = standards or RestStandardProvider()
    providers_fix = fixtures or RestFixtureProvider()

    standard: StandardTarget = providers_std.get_target(payload.activityId)
    if payload.maxOverdesign is not None:
        standard = replace(standard, max_overdesign=float(payload.maxOverdesign))
    target = TargetDto(
        avgLux=standard.avg_lux,
        uniformity=standard.uniformity,
        maxOverdesign=standard.max_overdesign,
    )

    application = payload.application
    if payload.variantIds:
        specs = providers_fix.get_variants(payload.variantIds, application)
    else:
        specs = providers_fix.list_main_variants(application)
    if not specs:
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "variantIds"),
                    "msg": f"No main-solution variants for application '{application}'.",
                    "type": "value_error",
                }
            ]
        )

    # Ratings AND opening size from the variant response (never the IES file):
    # rescale each loaded profile so physics flux == variant lumens (shape
    # from IES kept), and override length/width/height with variant dims
    # (meters, converted at the provider; None falls back to IES per axis).
    profiles = {}
    for spec in specs:
        profile = load_ies(spec.ies_text)
        profile = apply_variant_dimensions(profile, spec.length, spec.width, spec.height)
        if spec.lumens is not None:
            profile = scale_profile_to_lumens(profile, float(spec.lumens))
        profiles[spec.id] = profile
    wattages = {spec.id: float(spec.wattage) for spec in specs if spec.wattage is not None}
    lumens = {spec.id: float(spec.lumens) for spec in specs if spec.lumens is not None}

    options = PhysicsOptions(
        wall_reflectance=(
            payload.wallReflectance
            if payload.wallReflectance is not None
            else WALL_REFLECTANCE_FACTOR
        ),
        floor_reflectance=(
            payload.floorReflectance
            if payload.floorReflectance is not None
            else FLOOR_REFLECTANCE_FACTOR
        ),
        ceiling_reflectance=(
            payload.ceilingReflectance
            if payload.ceilingReflectance is not None
            else CEILING_REFLECTANCE_FACTOR
        ),
    )
    polygon = [(p.x, p.y) for p in payload.polygon]
    area = polygon_area(polygon)
    max_fixtures = _resolve_max_fixtures(payload, polygon)
    stage_b = _resolve_stage_b(payload, area)
    sx_range, sy_range = _resolve_spacing(payload, polygon)
    sx_vals = frange(sx_range.min, sx_range.max, sx_range.step)
    sy_vals = frange(sy_range.min, sy_range.max, sy_range.step)
    rotations = _resolve_rotations(payload, sx_vals, sy_vals)
    outcome = run_search(
        RoomInput(
            polygon=polygon,
            ceiling_height=payload.ceilingHeight,
            mounting_height=payload.mountingHeight,
            work_plane_height=payload.workPlaneHeight,
            floor_zone=payload.floorZone,
            wall_zone=payload.wallZone,
        ),
        profiles,
        standard,
        sx_vals,
        sy_vals,
        list(payload.search.offsetFractions),
        rotations,
        wattages=wattages,
        lumens=lumens,
        max_fixtures=max_fixtures,
        min_wall_clearance=payload.search.minWallClearance,
        shr_max=payload.search.shrMax,
        top_k=payload.topK,
        stage_b_n=stage_b,
        options=options,
    )
    grids = outcome.grids
    floor_patches = grids.floor if grids is not None else []
    floor_meta = dict(grids.floor_meta) if grids is not None else {}
    if grids is not None:
        floor_meta["workPlaneHeight"] = grids.work_z
    return AutomateResponse(
        target=target,
        application=application,
        solutions=[_solution(s, payload.mountingHeight, True, True) for s in outcome.solutions]
        + [_solution(s, payload.mountingHeight, False, True) for s in outcome.overcap],
        evaluatedA=outcome.evaluated_a,
        evaluatedB=outcome.evaluated_b,
        pruned=outcome.pruned,
        closestMiss=(
            _solution(outcome.closest_miss, payload.mountingHeight, False, False)
            if outcome.closest_miss else None
        ),
        appliedSpacingX=AppliedSpacingDto(min=sx_range.min, max=sx_range.max, step=sx_range.step),
        appliedSpacingY=AppliedSpacingDto(min=sy_range.min, max=sy_range.max, step=sy_range.step),
        floorPatches=[_patch(p) for p in floor_patches],
        floorMeta=floor_meta,
    )


def _resolve_spacing(
    payload: AutomateRequest, polygon: list[tuple[float, float]]
) -> tuple[SpacingRange, SpacingRange]:
    """Fill auto (None) spacing ranges from room size + mounting height.

    Explicit ranges pass through untouched; the resolved pair is capped at
    _MAX_CANDIDATES combos (422 otherwise) so auto can never blow up.
    """
    search = payload.search
    if search.spacingX is not None and search.spacingY is not None:
        return search.spacingX, search.spacingY
    multiplier = len(search.offsetFractions) * len(search.rotations)
    lo, hi, step = auto_spacing_range(
        polygon, payload.mountingHeight, search.shrMax, multiplier, _MAX_CANDIDATES,
    )
    auto = SpacingRange(min=lo, max=hi, step=step)
    sx_range = search.spacingX if search.spacingX is not None else auto
    sy_range = search.spacingY if search.spacingY is not None else auto
    n = candidate_count(
        sx_range, sy_range, len(search.offsetFractions), len(search.rotations)
    )
    if n > _MAX_CANDIDATES:
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "search"),
                    "msg": f"Search space has {n} candidates (max {_MAX_CANDIDATES}); widen steps.",
                    "type": "value_error",
                }
            ]
        )
    return sx_range, sy_range


def _resolve_max_fixtures(payload: AutomateRequest, polygon: list[tuple[float, float]]) -> int:
    """Auto-scale maxFixtures for vast spaces when not explicitly overridden."""
    if "maxFixtures" in payload.search.model_fields_set:
        return payload.search.maxFixtures
    area = polygon_area(polygon)
    return max(payload.search.maxFixtures, int(area / 10.0))


def _resolve_stage_b(payload: AutomateRequest, area: float) -> int:
    """Scale Stage-B budget for vast spaces when not explicitly overridden."""
    if "stageB" in payload.model_fields_set:
        return payload.stageB
    if area > 1000.0:
        return 2
    return payload.stageB


def _resolve_rotations(
    payload: AutomateRequest, sx_vals: list[float], sy_vals: list[float]
) -> list[float]:
    """Prune redundant 90° rotation when sx and sy are identical ranges."""
    if "rotations" in payload.search.model_fields_set:
        return list(payload.search.rotations)
    if sx_vals == sy_vals:
        return [0.0]
    return list(payload.search.rotations)


def _solution(
    sol: Solution, mounting_height: float, recommended: bool, with_heatmap: bool
) -> SolutionDto:
    return SolutionDto(
        variantId=sol.variant_key,
        fixtureCount=sol.count,
        placements=[
            AutomatePlacementDto(
                id=p.id, x=p.x, y=p.y, z=mounting_height,
                rotation=p.rotation if p.rotation is not None else 0.0,
                tiltAngle=0.0,  # the search only generates straight-down fixtures
            )
            for p in sol.placements
        ],
        grid=GridHintDto(
            spacingX=sol.spec.sx, spacingY=sol.spec.sy,
            offsetX=sol.spec.ox, offsetY=sol.spec.oy, rotation=sol.spec.rotation,
        ),
        fixtures=[
            AutomateFixtureDto(
                id=f.id,
                position=Vec3Dto(x=f.position[0], y=f.position[1], z=f.position[2]),
                rotation=f.rotation,
                tiltAngle=0.0,  # the search only generates straight-down fixtures
                length=f.length,
                width=f.width,
                height=f.height,
                corners=[Vec3Dto(x=c[0], y=c[1], z=c[2]) for c in f.corners],
                elements=[Vec3Dto(x=e[0], y=e[1], z=e[2]) for e in f.elements],
            )
            for f in sol.fixtures
        ],
        average=sol.average,
        minimum=sol.minimum,
        maximum=sol.maximum,
        uniformity=sol.uniformity,
        overdesign=sol.overdesign,
        powerW=sol.power_w,
        powerDensity=sol.power_density,
        missReason=sol.miss_reason,
        recommended=recommended,
        totalFloor=MatrixDto(values=list(sol.floor_values), metadata={}) if with_heatmap else None,
    )


def _patch(patch) -> PatchDto:
    return PatchDto(
        id=patch.id,
        surfaceType=patch.surface_type,
        parentId=patch.parent_id,
        center=Vec3Dto(x=patch.center[0], y=patch.center[1], z=patch.center[2]),
        normal=Vec3Dto(x=patch.normal[0], y=patch.normal[1], z=patch.normal[2]),
        area=patch.area,
        size=patch.size,
    )
