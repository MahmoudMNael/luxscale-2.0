"""V2 Calculation Controller for LuxScale.

Supports:
- Parametric pattern expansion (grid, staggered, linear, circumference)
- Multiple workplane evaluation in LuxCore
- Rotation and tilt angles (no client aim vectors)
- Free fixture placements and customizable grid/slots
- Unrestricted SC-Admin variant lookup (indoor/outdoor, main or non-main)
- In-memory custom photometry asset dictionaries
"""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.domain.exceptions import AppError, GeometryError, NoFixturesError, ProviderError
from app.domain.models import FixturePlacement, IESProfile
from app.engine import (
    build_eval_grids,
    build_room,
    build_solver_cache,
    resolve_fixtures,
    run,
)
from app.engine.types import PhysicsOptions, RoomInput
from app.providers import (
    FixtureProvider,
    FixtureSpec,
    RestFixtureProvider,
    RestStandardProvider,
    StandardProvider,
    StandardTarget,
)
from app.schemas.calculate import (
    ComplianceResultDto,
    EvaluationDto,
    FixtureDto,
    MatrixDto,
)
from app.schemas.geometry import Vec3Dto
from app.services.calculate_service import (
    _check_compliance,
    _evaluation,
    _fixture,
    _matrix,
)
from app.schemas.v2.calculate import (
    EvaluationPointDto,
    V2CalculateRequest,
    V2CalculateResponse,
    V2WorkplaneInput,
    V2WorkplaneResultDto,
)
from app.services._luxcore_bridge import IesHandleCache
from app.services.calculate_service import _check_compliance, _patch
from app.services.ies_service import load_ies
from app.services.v2.pattern_resolver_service import resolve_pattern
from app.services.variant_photometrics import apply_variant_dimensions, scale_profile_to_lumens
from app.services.vector_math import polygon_area

router = APIRouter(prefix="/api/v2", tags=["V2 Calculation"])

DEFAULT_FALLBACK_IES = """IESNA:LM-63-2002
[TEST] LUXSCALE_DEFAULT
[MANUFAC] LuxLum Architectural
[LUMCAT] Troffer 600x600 Direct
TILT=NONE
1 3600 1 3 1 1 2 0.6 0.6 0.08
1.0 1.0 40.0
0 45 90
0
1000 700 0
"""


def _get_standard_provider() -> StandardProvider:
    return RestStandardProvider()


def _get_fixture_provider() -> FixtureProvider:
    return RestFixtureProvider()


@router.post(
    "/calculate",
    response_model=V2CalculateResponse,
    summary="V2 Multi-Workplane Photometric Radiosity Calculation",
    description="Calculates direct and indirect illuminance across arbitrary room shapes, multiple workplanes, free fixtures, and resolved parametric patterns.",
)
def calculate_v2(
    payload: V2CalculateRequest,
    fixture_provider: Annotated[FixtureProvider, Depends(_get_fixture_provider)],
    standard_provider: Annotated[StandardProvider, Depends(_get_standard_provider)],
) -> V2CalculateResponse:
    start_time = time.perf_counter()
    IesHandleCache.clear()

    # 1. Parse room geometry
    polygon = [(p.x, p.y) for p in payload.polygon]
    if len(polygon) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room polygon must contain at least 3 vertices.",
        )

    area = polygon_area(polygon)
    if area <= 0.001:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Room polygon area must be greater than zero.",
        )

    # 2. Gather all placements: free fixtures + resolved patterns (deduplicated by position)
    placements: list[FixturePlacement] = []
    seen_positions: set[tuple[float, float, float]] = set()

    if payload.fixtures:
        for f in payload.fixtures:
            rot = f.rotation if f.rotation is not None else 0.0
            tilt = f.tiltAngle if f.tiltAngle is not None else 0.0
            z = f.z if f.z is not None else payload.mountingHeight
            pos_key = (round(f.x, 3), round(f.y, 3), round(z, 3))
            if pos_key not in seen_positions:
                seen_positions.add(pos_key)
                placements.append(
                    FixturePlacement(
                        id=f.id or f"F_{len(placements) + 1}",
                        x=f.x,
                        y=f.y,
                        z=z,
                        rotation=rot,
                        tilt_angle=tilt,
                        variant_id=f.variantId,
                        ies_ref=f.iesRef,
                    )
                )

    if payload.patterns:
        for pat in payload.patterns:
            pat_placements = resolve_pattern(pat, polygon, payload.mountingHeight)
            for pp in pat_placements:
                pz = pp.z if pp.z is not None else payload.mountingHeight
                pos_key = (round(pp.x, 3), round(pp.y, 3), round(pz, 3))
                if pos_key not in seen_positions:
                    seen_positions.add(pos_key)
                    placements.append(pp)

    if not placements:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fixtures or patterns specified, or no fixtures fell inside the room polygon.",
        )

    # 3. Load / resolve IES profiles and variant specs
    profiles: dict[str, IESProfile] = {}
    specs_by_id: dict[str, FixtureSpec] = {}

    # 3a. In-memory custom assets
    for key, text in (payload.assets or {}).items():
        try:
            profiles[key] = load_ies(text)
        except Exception:
            pass

    # 3b. External catalog variants (unconstrained: indoor/outdoor, main or non-main)
    variant_ids_needed: set[str] = set()
    for p in placements:
        if p.variant_id and p.variant_id not in profiles:
            variant_ids_needed.add(p.variant_id)

    if variant_ids_needed:
        try:
            specs = fixture_provider.get_variants(list(variant_ids_needed), main_only=False)
            for s in specs:
                specs_by_id[s.id] = s
                base_prof = load_ies(s.ies_text)
                scaled_prof = scale_profile_to_lumens(base_prof, s.lumens) if s.lumens else base_prof
                prof = apply_variant_dimensions(scaled_prof, s.length, s.width, s.height)
                profiles[s.id] = prof
        except Exception:
            # Fallback for offline dev / missing variant
            pass

    # Ensure a default profile exists if needed
    if "default" not in profiles:
        profiles["default"] = load_ies(DEFAULT_FALLBACK_IES)

    # 4. Build room & options
    default_work_z = payload.workplanes[0].height if payload.workplanes else 0.85
    room_in = RoomInput(
        polygon=polygon,
        ceiling_height=payload.ceilingHeight,
        mounting_height=payload.mountingHeight,
        work_plane_height=default_work_z,
        floor_zone=0.5,
        wall_zone=None,
    )
    room, ceiling_h, mount_h, _ = build_room(room_in)

    options = PhysicsOptions(
        wall_reflectance=payload.wallReflectance,
        floor_reflectance=payload.floorReflectance,
        ceiling_reflectance=payload.ceilingReflectance,
        maintenance_factor=payload.maintenanceFactor,
        bounces=payload.bounces,
    )

    d_ref = next(iter(profiles)) if profiles else "default"
    engine_fixtures = resolve_fixtures(room, placements, profiles, mount_h, default_ref=d_ref)

    # 5. Multi-Workplane Evaluation
    workplanes_list = payload.workplanes if payload.workplanes else [V2WorkplaneInput()]
    workplane_results: dict[str, V2WorkplaneResultDto] = {}

    for wp in workplanes_list:
        wp_eval_grids = build_eval_grids(
            room,
            work_z=wp.height,
            floor_zone=wp.margin,
            wall_zone=None,
        )
        wp_solver_cache = build_solver_cache(room, wp_eval_grids, ceiling_h, options)
        wp_engine_result = run(engine_fixtures, room, wp_eval_grids, wp_solver_cache, options)

        # Lookup standard target if activityId is specified
        std_target: StandardTarget | None = None
        if wp.standardId:
            try:
                std_target = standard_provider.get_target(wp.standardId)
            except Exception:
                pass

        compliance_dto: ComplianceResultDto | None = None
        if std_target or wp.targetLux:
            from app.schemas.calculate import ComplianceTargetInput
            tgt_input = ComplianceTargetInput(
                activityId=wp.standardId,
                targetLux=wp.targetLux,
                targetUniformity=wp.targetUniformity,
            )
            compliance_dto = _check_compliance(wp_engine_result.evaluation, tgt_input, std_target)

        # Extract evaluation points
        eval_points = [
            EvaluationPointDto(
                x=round(patch.center[0], 3),
                y=round(patch.center[1], 3),
                z=round(patch.center[2], 3),
                lux=round(val, 1),
            )
            for patch, val in zip(wp_eval_grids.floor, wp_engine_result.total_floor.values)
        ]

        eval_dto = _evaluation(
            wp_eval_grids.floor,
            wp_engine_result.evaluation,
            wp_eval_grids.floor_meta,
            wp.height,
            wp.margin,
        )

        matrix_dto = _matrix(wp_engine_result.total_floor)

        workplane_results[wp.id] = V2WorkplaneResultDto(
            workplaneId=wp.id,
            name=wp.name,
            height=wp.height,
            margin=wp.margin,
            evaluation=eval_dto,
            matrix=matrix_dto,
            points=eval_points,
            compliance=compliance_dto,
        )

    # 6. Aggregate Power Metrics
    total_watts = 0.0
    for fix in engine_fixtures:
        v_key = fix.variant_id or fix.ies_ref
        spec = specs_by_id.get(v_key or "")
        if spec and spec.wattage is not None:
            total_watts += float(spec.wattage)
        else:
            total_watts += 40.0  # Default nominal wattage

    power_density = total_watts / area if area > 0 else 0.0

    # 7. Map resolved fixtures DTO
    fixtures_dto = [_fixture(f) for f in engine_fixtures]

    duration_ms = round((time.perf_counter() - start_time) * 1000.0, 1)

    return V2CalculateResponse(
        durationMs=duration_ms,
        fixtures=fixtures_dto,
        workplaneResults=workplane_results,
        primaryWorkplaneId=workplanes_list[0].id,
        totalPowerWatts=round(total_watts, 1),
        powerDensityWPerM2=round(power_density, 2),
        bounces=options.bounces,
    )
