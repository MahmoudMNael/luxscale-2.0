from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError

from app.engine import RoomInput
from app.optimize import Solution, frange
from app.optimize import optimize as run_search
from app.providers import (
    FixtureProvider,
    RestFixtureProvider,
    RestStandardProvider,
    StandardProvider,
    StandardTarget,
)
from app.schemas.calculate import FixturePlacementDto
from app.schemas.errors import ErrorResponse
from app.schemas.optimize import GridHintDto, OptimizeRequest, OptimizeResponse, SolutionDto, TargetDto
from app.services.ies_service import installed_flux, load_ies

router = APIRouter()


def _standard_provider() -> StandardProvider:
    return RestStandardProvider()


def _fixture_provider() -> FixtureProvider:
    return RestFixtureProvider()


def _payload(payload: Annotated[str, Form(media_type="application/json")]) -> OptimizeRequest:
    try:
        return OptimizeRequest.model_validate_json(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    responses={
        400: {"model": ErrorResponse, "description": "IES, geometry or provider error"},
        422: {"model": ErrorResponse, "description": "Request validation failed"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
async def optimize(
    payload: Annotated[OptimizeRequest, Depends(_payload)],
    iesFiles: Annotated[
        list[UploadFile], File(description="IES files; filename = fixture id")
    ] = [],
    standards: Annotated[StandardProvider, Depends(_standard_provider)] = None,  # type: ignore[assignment]
    fixtures: Annotated[FixtureProvider, Depends(_fixture_provider)] = None,  # type: ignore[assignment]
) -> OptimizeResponse:
    providers_std = standards or RestStandardProvider()
    providers_fix = fixtures or RestFixtureProvider()
    target = (
        payload.target
        if payload.target is not None
        else _dto_from_target(providers_std.get_target(payload.activityId or ""))
    )
    standard = StandardTarget(
        activity_id=payload.activityId or "inline",
        avg_lux=target.avgLux,
        uniformity=target.uniformity,
        max_overdesign=target.maxOverdesign,
    )
    catalog: dict[str, str] = {}
    wattages: dict[str, float] = {}
    rated: dict[str, float] = {}
    for extra in iesFiles:
        name = extra.filename or f"fixture-{len(catalog)}"
        catalog[name] = (await extra.read()).decode("utf-8")
        if payload.power and name in payload.power:
            wattages[name] = payload.power[name]
    for fid in payload.fixtureIds or []:
        spec = providers_fix.get_one(fid)
        catalog[spec.id] = spec.ies_text
        if spec.wattage is not None:
            wattages[spec.id] = spec.wattage
        if spec.lumens is not None:
            rated[spec.id] = spec.lumens
    if not catalog:
        raise RequestValidationError(
            [{"loc": ("body", "iesFiles"), "msg": "No fixtures: upload iesFiles or give fixtureIds.",
              "type": "missing"}]
        )
    profiles = {key: load_ies(text) for key, text in catalog.items()}
    lumens = {key: rated.get(key, installed_flux(profile)) for key, profile in profiles.items()}
    outcome = run_search(
        RoomInput(
            polygon=[(p.x, p.y) for p in payload.polygon],
            ceiling_height=(
                payload.ceilingHeight if payload.ceilingHeight is not None else payload.height
            ),
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
    )
    return OptimizeResponse(
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


def _dto_from_target(standard: StandardTarget) -> TargetDto:
    return TargetDto(
        avgLux=standard.avg_lux, uniformity=standard.uniformity,
        maxOverdesign=standard.max_overdesign,
    )
