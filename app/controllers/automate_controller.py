from __future__ import annotations

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
from app.engine import PhysicsOptions, RoomInput
from app.providers import (
    FixtureProvider,
    RestFixtureProvider,
    RestStandardProvider,
    StandardProvider,
    StandardTarget,
)
from app.schemas.automate import (
    AutomateRequest,
    AutomateResponse,
    GridHintDto,
    SolutionDto,
    TargetDto,
)
from app.schemas.calculate import FixturePlacementDto
from app.schemas.errors import ErrorResponse
from app.services.ies_service import load_ies
from app.services.variant_photometrics import scale_profile_to_lumens

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

    - Target from `GET {STANDARDS_BASE_URL}/api/v1/standards/{activityId}`.
    - Application from mounting height: >= 3.0 -> industrial else interior
      (see `application_for_mounting_height` in schemas/automate.py).
    - Variants: explicit `variantIds` or all main-solution variants for the
      application (`is_main_solution=true` filter, provider-side).
    - IES shape from each variant's `ies_file_id` asset bytes; watts/lumens
      from `variant.power`/`variant.efficacy` via variant_photometrics.
    """
    providers_std = standards or RestStandardProvider()
    providers_fix = fixtures or RestFixtureProvider()

    standard: StandardTarget = providers_std.get_target(payload.activityId)
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

    # Ratings from the variant response (never the IES file): rescale each
    # loaded profile so physics flux == variant lumens (shape from IES kept).
    profiles = {}
    for spec in specs:
        profile = load_ies(spec.ies_text)
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
    outcome = run_search(
        RoomInput(
            polygon=[(p.x, p.y) for p in payload.polygon],
            ceiling_height=payload.ceilingHeight,
            mounting_height=payload.mountingHeight,
            work_plane_height=payload.workPlaneHeight,
            floor_zone=payload.floorZone,
            wall_zone=payload.wallZone,
        ),
        profiles,
        standard,
        frange(payload.search.spacingX.min, payload.search.spacingX.max, payload.search.spacingX.step),
        frange(payload.search.spacingY.min, payload.search.spacingY.max, payload.search.spacingY.step),
        list(payload.search.offsetFractions),
        list(payload.search.rotations),
        wattages=wattages,
        lumens=lumens,
        max_fixtures=payload.search.maxFixtures,
        min_wall_clearance=payload.search.minWallClearance,
        shr_max=payload.search.shrMax,
        top_k=payload.topK,
        stage_b_n=payload.stageB,
        options=options,
    )
    return AutomateResponse(
        target=target,
        solutions=[_solution(s) for s in outcome.solutions],
        evaluatedA=outcome.evaluated_a,
        evaluatedB=outcome.evaluated_b,
        pruned=outcome.pruned,
        closestMiss=_solution(outcome.closest_miss) if outcome.closest_miss else None,
    )


def _solution(sol: Solution) -> SolutionDto:
    return SolutionDto(
        fixtureId=sol.fixture_key,
        fixtureCount=sol.count,
        placements=[
            FixturePlacementDto(id=p.id, x=p.x, y=p.y, z=p.z, rotation=p.rotation)
            for p in sol.placements
        ],
        grid=GridHintDto(
            spacingX=sol.spec.sx, spacingY=sol.spec.sy,
            offsetX=sol.spec.ox, offsetY=sol.spec.oy, rotation=sol.spec.rotation,
        ),
        average=sol.average,
        minimum=sol.minimum,
        maximum=sol.maximum,
        uniformity=sol.uniformity,
        overdesign=sol.overdesign,
        powerW=sol.power_w,
        powerDensity=sol.power_density,
    )
