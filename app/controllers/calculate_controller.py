from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.domain.exceptions import IesParseError
from app.domain.models import IESProfile
from app.providers import (
    FixtureProvider,
    FixtureSpec,
    RestFixtureProvider,
    RestStandardProvider,
    StandardProvider,
    StandardTarget,
)
from app.schemas.calculate import CalculateRequest, CalculateResponse
from app.schemas.errors import ErrorResponse
from app.services import calculate_service
from app.services.ies_service import load_ies
from app.services.variant_photometrics import apply_variant_dimensions, scale_profile_to_lumens

router = APIRouter()

_ERROR = {
    "model": ErrorResponse,
    "content": {
        "application/json": {
            "examples": {
                "ies_parse": {
                    "summary": "Unusable IES file",
                    "value": {
                        "error": {
                            "code": "IES_PARSE",
                            "message": "IES file must declare TILT=NONE.",
                            "details": None,
                            "requestId": "00000000-0000-0000-0000-000000000000",
                        }
                    },
                },
                "geometry": {
                    "summary": "Degenerate room",
                    "value": {
                        "error": {
                            "code": "GEOMETRY_INVALID",
                            "message": "Room polygon must have non-zero area.",
                            "details": None,
                            "requestId": "00000000-0000-0000-0000-000000000000",
                        }
                    },
                },
                "no_fixtures": {
                    "summary": "Grid missed the room",
                    "value": {
                        "error": {
                            "code": "NO_FIXTURES",
                            "message": "No fixtures fall inside the room polygon for the given grid.",
                            "details": None,
                            "requestId": "00000000-0000-0000-0000-000000000000",
                        }
                    },
                },
            }
        }
    },
}


def _standard_provider() -> StandardProvider:
    return RestStandardProvider()


def _fixture_provider() -> FixtureProvider:
    return RestFixtureProvider()


def _load_and_scale_variant_specs(
    variant_ids: list[str],
    prov: FixtureProvider,
    profiles: dict[str, IESProfile],
    specs_by_id: dict[str, FixtureSpec],
) -> None:
    if not variant_ids:
        return
    specs = prov.get_variants(variant_ids, main_only=False)
    for s in specs:
        specs_by_id[s.id] = s
        base_prof = load_ies(s.ies_text)
        scaled_prof = scale_profile_to_lumens(base_prof, s.lumens) if s.lumens else base_prof
        prof = apply_variant_dimensions(scaled_prof, s.length, s.width, s.height)
        profiles[s.id] = prof


@router.post(
    "/calculate",
    response_model=CalculateResponse,
    responses={
        400: {**_ERROR, "description": "IES or geometry cannot be used"},
        422: {
            "model": ErrorResponse,
            "description": "Request validation failed",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "Request validation failed.",
                            "details": [{"field": "payload.ceilingHeight", "issue": "Input should be greater than 0"}],
                            "requestId": "00000000-0000-0000-0000-000000000000",
                        }
                    }
                }
            },
        },
        500: {
            "model": ErrorResponse,
            "description": "Internal server error",
            "content": {
                "application/json": {
                    "example": {
                        "error": {
                            "code": "INTERNAL_ERROR",
                            "message": "Internal server error.",
                            "details": None,
                            "requestId": "00000000-0000-0000-0000-000000000000",
                        }
                    }
                }
            },
        },
    },
)
async def calculate(
    request: Request,
    standards: Annotated[StandardProvider, Depends(_standard_provider)] = None,  # type: ignore[assignment]
    fixtures: Annotated[FixtureProvider, Depends(_fixture_provider)] = None,  # type: ignore[assignment]
) -> CalculateResponse:
    """Calculates illuminance and uniformity for a given room layout.

    Supports both:
    1. Pure JSON (application/json) referencing catalog variantId or per-fixture variantId/iesRef.
    2. Multipart form-data (multipart/form-data) uploading raw IES file(s) + payload JSON string.
    """
    content_type = request.headers.get("content-type", "")
    profiles: dict[str, IESProfile] = {}
    specs_by_id: dict[str, FixtureSpec] = {}
    default_ref: str | None = None
    fix_prov = fixtures or _fixture_provider()
    std_prov = standards or _standard_provider()

    if "application/json" in content_type:
        try:
            body = await request.json()
        except Exception as exc:
            raise RequestValidationError(
                [{"loc": ("body",), "msg": "Invalid JSON body", "type": "json_invalid"}]
            ) from exc
        try:
            payload = CalculateRequest.model_validate(body)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc

        needed_variants = set()
        if payload.variantId:
            needed_variants.add(payload.variantId)
        for f in payload.fixtures or []:
            if f.variantId:
                needed_variants.add(f.variantId)
            elif f.iesRef and not f.iesRef.endswith((".ies", ".ldt", ".txt")):
                needed_variants.add(f.iesRef)

        _load_and_scale_variant_specs(list(needed_variants), fix_prov, profiles, specs_by_id)

        if not profiles:
            raise RequestValidationError(
                [
                    {
                        "loc": ("body", "variantId"),
                        "msg": "Either variantId or IES photometry must be specified.",
                        "type": "missing",
                    }
                ]
            )

        if payload.variantId and payload.variantId in profiles:
            default_ref = payload.variantId
        else:
            default_ref = next(iter(profiles))

    else:
        # Multipart / form-data handling (legacy & file upload mode)
        try:
            form = await request.form()
        except Exception as exc:
            raise RequestValidationError(
                [{"loc": ("body",), "msg": "Invalid form data", "type": "form_invalid"}]
            ) from exc

        payload_raw = form.get("payload")
        if payload_raw is None:
            raise RequestValidationError(
                [{"loc": ("body", "payload"), "msg": "Field 'payload' is required in form-data.", "type": "missing"}]
            )
        try:
            if isinstance(payload_raw, str):
                payload = CalculateRequest.model_validate_json(payload_raw)
            else:
                payload = CalculateRequest.model_validate(payload_raw)
        except ValidationError as exc:
            raise RequestValidationError(exc.errors()) from exc

        ies_file = form.get("iesFile")
        ies_files = form.getlist("iesFiles")
        uploaded_default: str | None = None

        if ies_file is not None and hasattr(ies_file, "read"):
            name = getattr(ies_file, "filename", None) or "default"
            content = await ies_file.read()
            text = content.decode("utf-8")
            profiles[name] = load_ies(text)
            uploaded_default = name

        for extra in ies_files:
            if extra is not None and hasattr(extra, "read"):
                name = getattr(extra, "filename", None) or f"fixture-{len(profiles)}"
                content = await extra.read()
                text = content.decode("utf-8")
                profiles[name] = load_ies(text)
                if uploaded_default is None:
                    uploaded_default = name

        needed_variants = set()
        if payload.variantId:
            needed_variants.add(payload.variantId)
        for f in payload.fixtures or []:
            if f.variantId:
                needed_variants.add(f.variantId)
            elif f.iesRef and f.iesRef not in profiles and not f.iesRef.endswith((".ies", ".ldt", ".txt")):
                needed_variants.add(f.iesRef)

        _load_and_scale_variant_specs(list(needed_variants), fix_prov, profiles, specs_by_id)

        if not profiles:
            raise RequestValidationError(
                [
                    {
                        "loc": ("body", "iesFile"),
                        "msg": "At least one IES file or variantId is required.",
                        "type": "missing",
                    }
                ]
            )

        if payload.variantId and payload.variantId in profiles:
            default_ref = payload.variantId
        elif uploaded_default:
            default_ref = uploaded_default
        elif "default" in profiles:
            default_ref = "default"
        else:
            default_ref = next(iter(profiles))

    # Validate that every placement has a resolved profile
    if payload.fixtures:
        for f in payload.fixtures:
            ref = f.variantId or f.iesRef or default_ref
            if not ref or (ref not in profiles and f.iesRef not in profiles and f.variantId not in profiles):
                raise RequestValidationError(
                    [
                        {
                            "loc": ("body", "fixtures", f.id or "fixture"),
                            "msg": f"Fixture references unknown variantId/iesRef '{f.variantId or f.iesRef}'.",
                            "type": "value_error",
                        }
                    ]
                )
    elif payload.grid:
        if not default_ref or default_ref not in profiles:
            raise RequestValidationError(
                [
                    {
                        "loc": ("body", "variantId"),
                        "msg": "variantId or default IES file must be provided for grid layouts.",
                        "type": "missing",
                    }
                ]
            )

    standard_target: StandardTarget | None = None
    if payload.compliance and payload.compliance.activityId:
        standard_target = std_prov.get_target(payload.compliance.activityId)

    return calculate_service.calculate_extended(
        payload=payload,
        profiles=profiles,
        specs_by_id=specs_by_id,
        default_ref=default_ref,
        standard_target=standard_target,
    )
