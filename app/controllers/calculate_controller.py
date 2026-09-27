from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError

from app.domain.exceptions import IesParseError
from app.schemas.calculate import CalculateRequest, CalculateResponse
from app.schemas.errors import ErrorResponse
from app.services import calculate_service
from app.services.ies_service import load_ies

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


def _payload(payload: Annotated[str, Form(media_type="application/json")]) -> CalculateRequest:
    try:
        return CalculateRequest.model_validate_json(payload)
    except ValidationError as exc:
        raise RequestValidationError(exc.errors()) from exc


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
                            "details": [{"field": "payload.height", "issue": "Input should be greater than 0"}],
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
    payload: Annotated[CalculateRequest, Depends(_payload)],
    iesFile: Annotated[UploadFile | None, File(description="Default IES LM-63 photometry file")] = None,
    iesFiles: Annotated[
        list[UploadFile], File(description="Extra IES files keyed by filename for per-fixture iesRef")
    ] = [],
) -> CalculateResponse:
    """Single default file (legacy) or many files matched by fixture iesRef."""
    texts: dict[str, str] = {}
    if iesFile is not None:
        texts[iesFile.filename or "default"] = (await iesFile.read()).decode("utf-8")
    for extra in iesFiles:
        texts[extra.filename or f"fixture-{len(texts)}"] = (await extra.read()).decode("utf-8")
    if not texts:
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "iesFile"),
                    "msg": "At least one IES file is required.",
                    "type": "missing",
                }
            ]
        )
    if len(texts) == 1 and not any(f.iesRef for f in payload.fixtures or []):
        # Legacy fast path: one profile shared by all fixtures.
        return calculate_service.calculate(payload, next(iter(texts.values())))
    profiles = {name: load_ies(text) for name, text in texts.items()}
    default_ref = (
        (iesFile.filename or "default") if iesFile is not None else next(iter(profiles))
    )
    if default_ref not in profiles:  # pragma: no cover - defensive
        raise IesParseError("Default IES file is missing.")
    return calculate_service.calculate_with_profiles(payload, profiles, default_ref=default_ref)
