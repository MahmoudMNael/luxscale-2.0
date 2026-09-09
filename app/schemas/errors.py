from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    IES_PARSE = "IES_PARSE"
    IES_ENCODING = "IES_ENCODING"
    GEOMETRY_INVALID = "GEOMETRY_INVALID"
    NO_FIXTURES = "NO_FIXTURES"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ErrorDetail(BaseModel):
    field: str | None = Field(None, description="JSON path of the invalid field, when known")
    issue: str = Field(..., description="What was wrong with that field")


class ErrorBody(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    code: ErrorCode = Field(..., description="Stable machine-readable error code")
    message: str = Field(..., description="Client-safe explanation")
    details: list[ErrorDetail] | None = Field(
        None,
        description="Per-field issues for validation errors",
    )
    request_id: str = Field(..., alias="requestId", description="Matches the X-Request-ID response header")


class ErrorResponse(BaseModel):
    error: ErrorBody
