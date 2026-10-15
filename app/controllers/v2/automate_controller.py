"""V2 Automate Controller for LuxScale.

Provides asynchronous background lighting studies:
- POST /api/v2/automate/jobs (dispatches study, returns jobId)
- GET /api/v2/automate/jobs/{job_id} (polls status & results)
- Supports drawn canvas grid constraint (V2GridSpec) or multi-grid exploration
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import replace
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status

from app.app_settings import (
    CEILING_REFLECTANCE_FACTOR,
    FLOOR_REFLECTANCE_FACTOR,
    WALL_REFLECTANCE_FACTOR,
)
from app.automate import Solution, frange
from app.automate import automate as run_search
from app.automate.layouts import auto_spacing_range
from app.controllers.automate_controller import _patch, _solution
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
    AutomateResponse,
    SpacingRange,
    TargetDto,
    _MAX_CANDIDATES,
    application_for_mounting_height,
    candidate_count,
)
from app.schemas.v2.automate import (
    V2AutomateJobResponse,
    V2AutomateRequest,
)
from app.services.ies_service import load_ies
from app.services.variant_photometrics import apply_variant_dimensions, scale_profile_to_lumens
from app.services.vector_math import polygon_area

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/automate", tags=["V2 Automate"])

# In-memory job registry for asynchronous studies
_automate_jobs: dict[str, dict] = {}


def _standard_provider() -> StandardProvider:
    return RestStandardProvider()


def _fixture_provider() -> FixtureProvider:
    return RestFixtureProvider()


def _run_automate_sync(
    job_id: str,
    payload: V2AutomateRequest,
    standards: StandardProvider,
    fixtures: FixtureProvider,
) -> None:
    """Synchronous CPU worker executed in background thread."""
    try:
        _automate_jobs[job_id]["status"] = "running"
        _automate_jobs[job_id]["updatedAt"] = time.time()

        polygon = [(p.x, p.y) for p in payload.polygon]
        area = polygon_area(polygon)
        if area <= 0.001:
            raise ValueError("Room polygon area must be greater than zero.")

        # 1. Resolve Target
        standard: StandardTarget
        if payload.activityId:
            try:
                standard = standards.get_target(payload.activityId)
            except Exception as err:
                logger.warning(f"Standard provider failed for {payload.activityId}: {err}")
                standard = StandardTarget(
                    activity_id=payload.activityId,
                    avg_lux=payload.targetLux or 500.0,
                    uniformity=payload.targetUniformity or 0.6,
                    max_overdesign=payload.maxOverdesign if payload.maxOverdesign is not None else 0.3,
                )
        else:
            standard = StandardTarget(
                activity_id="custom",
                avg_lux=payload.targetLux or 500.0,
                uniformity=payload.targetUniformity or 0.6,
                max_overdesign=payload.maxOverdesign if payload.maxOverdesign is not None else 0.3,
            )

        if payload.maxOverdesign is not None:
            standard = replace(standard, max_overdesign=float(payload.maxOverdesign))

        target = TargetDto(
            avgLux=standard.avg_lux,
            uniformity=standard.uniformity,
            maxOverdesign=standard.max_overdesign,
        )

        # 2. Resolve Variants
        application = application_for_mounting_height(payload.mountingHeight)
        if payload.variantIds:
            # When variants are specifically specified, bypass main_solution and application validations
            specs = fixtures.get_variants(payload.variantIds, application=None, main_only=False)
        else:
            # Only if no variants are chosen, filter by interior/industrial rule and main solution
            specs = fixtures.list_main_variants(application)

        if not specs:
            raise ValueError(
                f"No luminaire variants available{' for specified IDs' if payload.variantIds else f' for application {application}'}."
            )

        # 3. Load IES Photometrics
        profiles = {}
        for spec in specs:
            profile = load_ies(spec.ies_text)
            profile = apply_variant_dimensions(profile, spec.length, spec.width, spec.height)
            if spec.lumens is not None:
                profile = scale_profile_to_lumens(profile, float(spec.lumens))
            profiles[spec.id] = profile

        wattages = {spec.id: float(spec.wattage) for spec in specs if spec.wattage is not None}
        lumens = {spec.id: float(spec.lumens) for spec in specs if spec.lumens is not None}

        # 4. Physics Options
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

        # 5. Grid Resolution: Canvas Grid constraint vs Multi-Grid exploration
        sx_range: SpacingRange
        sy_range: SpacingRange
        sx_vals: list[float]
        sy_vals: list[float]
        offset_fractions: list[float]
        rotations: list[float]

        if payload.gridSpec is not None:
            # Constrained to the drawn canvas grid
            gs = payload.gridSpec
            sx_range = SpacingRange(min=gs.spacingX, max=gs.spacingX, step=1.0)
            sy_range = SpacingRange(min=gs.spacingY, max=gs.spacingY, step=1.0)
            sx_vals = [gs.spacingX]
            sy_vals = [gs.spacingY]
            offset_fractions = [gs.offsetFraction]
            rotations = [gs.rotation]
        else:
            # Multi-grid automatic exploration
            multiplier = 1 * 2  # default offsets & rotations
            lo, hi, step = auto_spacing_range(
                polygon, payload.mountingHeight, 1.5, multiplier, _MAX_CANDIDATES
            )
            auto = SpacingRange(min=lo, max=hi, step=step)
            sx_range = auto
            sy_range = auto
            sx_vals = frange(sx_range.min, sx_range.max, sx_range.step)
            sy_vals = frange(sy_range.min, sy_range.max, sy_range.step)
            rotations = [0.0] if sx_vals == sy_vals else [0.0, 90.0]
            offset_fractions = [0.5]

        max_fixtures = max(64, int(area / 10.0))
        stage_b = payload.stageB if payload.stageB is not None else (2 if area > 1000.0 else 12)

        # 6. Execute Automate Search
        outcome = run_search(
            RoomInput(
                polygon=polygon,
                ceiling_height=payload.ceilingHeight,
                mounting_height=payload.mountingHeight,
                work_plane_height=payload.workPlaneHeight,
                floor_zone=payload.floorZone,
                wall_zone=None,
            ),
            profiles,
            standard,
            sx_vals,
            sy_vals,
            offset_fractions,
            rotations,
            wattages=wattages,
            lumens=lumens,
            max_fixtures=max_fixtures,
            min_wall_clearance=0.0,
            shr_max=1.5,
            top_k=payload.topK,
            stage_b_n=stage_b,
            options=options,
        )

        grids = outcome.grids
        floor_patches = grids.floor if grids is not None else []
        floor_meta = dict(grids.floor_meta) if grids is not None else {}
        if grids is not None:
            floor_meta["workPlaneHeight"] = grids.work_z

        response = AutomateResponse(
            target=target,
            application=application,
            solutions=[_solution(s, payload.mountingHeight, True, True, floor_patches) for s in outcome.solutions]
            + [_solution(s, payload.mountingHeight, False, True, floor_patches) for s in outcome.overcap],
            evaluatedA=outcome.evaluated_a,
            evaluatedB=outcome.evaluated_b,
            pruned=outcome.pruned,
            closestMiss=(
                _solution(outcome.closest_miss, payload.mountingHeight, False, False, floor_patches)
                if outcome.closest_miss else None
            ),
            appliedSpacingX=AppliedSpacingDto(min=sx_range.min, max=sx_range.max, step=sx_range.step),
            appliedSpacingY=AppliedSpacingDto(min=sy_range.min, max=sy_range.max, step=sy_range.step),
            floorPatches=[_patch(p) for p in floor_patches],
            floorMeta=floor_meta,
        )

        _automate_jobs[job_id]["status"] = "completed"
        _automate_jobs[job_id]["result"] = response.model_dump(by_alias=True)
        _automate_jobs[job_id]["updatedAt"] = time.time()
    except Exception as err:
        logger.exception(f"Automate job {job_id} failed: {err}")
        _automate_jobs[job_id]["status"] = "failed"
        _automate_jobs[job_id]["error"] = str(err)
        _automate_jobs[job_id]["updatedAt"] = time.time()


@router.post(
    "/jobs",
    response_model=V2AutomateJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Dispatch V2 Automate Lighting Study Job",
)
async def create_automate_job(
    payload: V2AutomateRequest,
    background_tasks: BackgroundTasks,
    standards: Annotated[StandardProvider, Depends(_standard_provider)] = None,  # type: ignore[assignment]
    fixtures: Annotated[FixtureProvider, Depends(_fixture_provider)] = None,  # type: ignore[assignment]
) -> V2AutomateJobResponse:
    """Dispatches a background automate lighting study job."""
    if payload.mountingHeight > payload.ceilingHeight:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mountingHeight cannot exceed ceilingHeight",
        )
    if len(payload.polygon) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room polygon must contain at least 3 vertices",
        )

    job_id = str(uuid.uuid4())
    now = time.time()
    job_record = {
        "jobId": job_id,
        "status": "pending",
        "createdAt": now,
        "updatedAt": now,
        "result": None,
        "error": None,
    }
    _automate_jobs[job_id] = job_record

    providers_std = standards or RestStandardProvider()
    providers_fix = fixtures or RestFixtureProvider()

    # Dispatch to background thread so FastAPI event loop remains responsive
    background_tasks.add_task(
        _run_automate_sync,
        job_id,
        payload,
        providers_std,
        providers_fix,
    )

    return V2AutomateJobResponse(
        jobId=job_id,
        status="pending",
        createdAt=now,
        updatedAt=now,
    )


@router.get(
    "/jobs/{job_id}",
    response_model=V2AutomateJobResponse,
    summary="Poll V2 Automate Job Status",
)
async def get_automate_job(job_id: str) -> V2AutomateJobResponse:
    """Returns the current state and results of an automate job."""
    job = _automate_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Automate job '{job_id}' not found.",
        )
    return V2AutomateJobResponse(**job)
