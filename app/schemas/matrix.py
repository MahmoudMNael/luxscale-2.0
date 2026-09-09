from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MatrixDto(BaseModel):
    values: list[float] = Field(..., description="One illuminance (lux) per patch, same order as the patch list")
    metadata: dict[str, Any] = Field(default_factory=dict)
