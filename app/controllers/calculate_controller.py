from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import ValidationError
from fastapi.exceptions import RequestValidationError

from app.schemas.calculate import CalculateRequest, CalculateResponse
from app.schemas.errors import ErrorResponse
from app.services import calculate_service

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
    iesFile: Annotated[UploadFile, File(description="IES LM-63 photometry text file")],
) -> CalculateResponse:
    ies_text = (await iesFile.read()).decode("utf-8")
    return calculate_service.calculate(payload, ies_text)
