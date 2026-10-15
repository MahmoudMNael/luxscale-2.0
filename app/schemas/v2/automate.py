from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from app.app_settings import (
    CEILING_REFLECTANCE_FACTOR,
    FLOOR_REFLECTANCE_FACTOR,
    WALL_REFLECTANCE_FACTOR,
)
from app.schemas.automate import AutomateResponse
from app.schemas.geometry import Point2D


class V2GridSpec(BaseModel):
    """Specific grid pattern to test (e.g. from drawn canvas grid)."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    spacingX: float = Field(..., gt=0, description="Column spacing along X, meters")
    spacingY: float = Field(..., gt=0, description="Row spacing along Y, meters")
    offsetX: float | None = Field(default=None, description="Perimeter X offset, meters")
    offsetY: float | None = Field(default=None, description="Perimeter Y offset, meters")
    rotation: float = Field(default=0.0, description="Grid rotation angle in degrees")
    offsetFraction: float = Field(default=0.5, ge=0.0, le=1.0, description="Offset fraction of spacing")


class V2AutomateRequest(BaseModel):
    """V2 Automate lighting study request."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    polygon: list[Point2D] = Field(..., min_length=3, description="Room footprint polygon")
    ceilingHeight: float = Field(..., gt=0, description="Room ceiling height in meters")
    mountingHeight: float = Field(..., gt=0, description="Fixture mounting height in meters")
    workPlaneHeight: float = Field(default=0.0, ge=0.0, description="Workplane height in meters")
    floorZone: float | None = Field(default=0.5, ge=0.0, description="Floor margin zone in meters")
    wallReflectance: float | None = Field(
        default=None, ge=0.0, le=1.0, description=f"Wall reflectance (default {WALL_REFLECTANCE_FACTOR})"
    )
    floorReflectance: float | None = Field(
        default=None, ge=0.0, le=1.0, description=f"Floor reflectance (default {FLOOR_REFLECTANCE_FACTOR})"
    )
    ceilingReflectance: float | None = Field(
        default=None, ge=0.0, le=1.0, description=f"Ceiling reflectance (default {CEILING_REFLECTANCE_FACTOR})"
    )
    activityId: str | None = Field(default=None, description="Standard activity ID (e.g. from EN 12464)")
    targetLux: float | None = Field(default=None, gt=0, description="Custom target illuminance in lux")
    targetUniformity: float | None = Field(default=None, ge=0.0, le=1.0, description="Custom target uniformity U0")
    maxOverdesign: float | None = Field(default=0.3, ge=0.0, description="Allowed excess illuminance ratio")
    variantIds: list[str] | None = Field(
        default=None, description="Selected luminaire variant UUIDs; None or empty = all main variants"
    )
    gridSpec: V2GridSpec | None = Field(
        default=None, description="Drawn canvas grid spec. If None, systematically explores multiple grids"
    )
    topK: int = Field(default=5, ge=1, le=20, description="Number of solutions to return")
    stageB: int = Field(default=12, ge=1, le=50, description="Stage B verification budget")


class V2AutomateJobResponse(BaseModel):
    """Automate job status and result response."""

    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    jobId: str
    status: Literal["pending", "running", "completed", "failed"]
    createdAt: float
    updatedAt: float
    result: AutomateResponse | None = None
    error: str | None = None
