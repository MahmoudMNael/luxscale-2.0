from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.calculate import (
    ComplianceResultDto,
    ComplianceTargetInput,
    EvaluationDto,
    FixtureDto,
    FixturePlacementDto,
)
from app.schemas.geometry import Point2D, Vec3Dto
from app.schemas.matrix import MatrixDto
from app.services.v2.pattern_resolver_service import ParametricPatternDto


class V2WorkplaneInput(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str = "WP-01"
    name: str = "Standard Task Plane"
    height: float = Field(default=0.85, ge=0.0, description="Height above finished floor (AFF), meters")
    margin: float = Field(default=0.5, ge=0.0, description="Perimeter wall inset margin, meters")
    standardId: str | None = Field(default=None, alias="standard_id")
    targetLux: float | None = Field(default=None, gt=0, alias="target_lux")
    targetUniformity: float | None = Field(default=None, ge=0, le=1, alias="target_uniformity")


class EvaluationPointDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    x: float
    y: float
    z: float
    lux: float


class V2WorkplaneResultDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    workplaneId: str
    name: str
    height: float
    margin: float
    evaluation: EvaluationDto
    matrix: MatrixDto
    points: list[EvaluationPointDto] = Field(default_factory=list)
    compliance: ComplianceResultDto | None = None


class V2CalculateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    polygon: list[Point2D] = Field(
        ...,
        min_length=3,
        description="Room footprint polygon vertices in meters",
    )
    ceilingHeight: float = Field(
        ...,
        gt=0,
        alias="ceiling_height",
        description="Ceiling plane height in meters",
    )
    mountingHeight: float = Field(
        ...,
        gt=0,
        alias="mounting_height",
        description="Fixture mounting height in meters",
    )
    fixtures: list[FixturePlacementDto] | None = Field(
        default=None,
        description="Discrete placed luminaires with position, rotation, and tilt angle",
    )
    patterns: list[ParametricPatternDto] | None = Field(
        default=None,
        description="Parametric array patterns (grid, staggered, linear, circumference) to resolve",
    )
    workplanes: list[V2WorkplaneInput] = Field(
        default_factory=lambda: [V2WorkplaneInput(id="WP-01")],
        description="List of target workplanes to evaluate in LuxCore",
    )
    wallReflectance: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        alias="wall_reflectance",
        description="Wall reflectance factor rho (default 0.5)",
    )
    floorReflectance: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        alias="floor_reflectance",
        description="Floor reflectance factor rho (default 0.2)",
    )
    ceilingReflectance: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        alias="ceiling_reflectance",
        description="Ceiling reflectance factor rho (default 0.7)",
    )
    maintenanceFactor: float = Field(
        default=0.8,
        gt=0.0,
        le=1.0,
        alias="maintenance_factor",
        description="Maintenance factor (default 0.8)",
    )
    bounces: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Radiosity inter-reflection bounces (0 = direct only, 3 = full radiosity)",
    )
    assets: dict[str, str] = Field(
        default_factory=dict,
        description="Optional in-memory photometry asset texts (assetId/fileName -> raw IES/LDT text)",
    )


class V2CalculateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    durationMs: float
    fixtures: list[FixtureDto]
    workplaneResults: dict[str, V2WorkplaneResultDto]
    primaryWorkplaneId: str
    totalPowerWatts: float
    powerDensityWPerM2: float
    bounces: int
