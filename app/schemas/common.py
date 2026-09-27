"""Shared wire types for the admin backend (envelope, pagination, decimal coercion).

Mirrors admin-api-contract.md §1. Frontend base URL prefix for all admin
endpoints is `/api/v1`. No auth headers required.
"""

from __future__ import annotations

from typing import Annotated, Any, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, Field


def _coerce_decimal(value: Any) -> float | None:
    """Accept contract Decimals as JSON string ("0.95") or number (0.95)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        return float(text)
    return float(value)  # let pydantic raise on anything else


DecimalFloat = Annotated[float, BeforeValidator(_coerce_decimal)]
OptionalDecimalFloat = Annotated[float | None, BeforeValidator(_coerce_decimal)]


class Pagination(BaseModel):
    total_count: int = Field(..., ge=0)
    page_size: int = Field(..., ge=1)
    current_page: int = Field(..., ge=1)
    total_pages: int = Field(..., ge=0)


T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    """Success envelope §1.1: { success: true, data, pagination }."""

    success: bool = True
    data: T
    pagination: Pagination | None = None


__all__ = ["DecimalFloat", "Envelope", "OptionalDecimalFloat", "Pagination"]
