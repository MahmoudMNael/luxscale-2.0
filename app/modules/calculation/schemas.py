from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from app.modules.projects.schemas import Point2DDto, Vec3DDto, SurfaceReflectancesDto


class V2FixtureInputDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    id: str
    x: float
    y: float
    z: float
    rotation: float = Field(default=0.0, ge=0.0, le=360.0)
    tiltAngle: float = Field(default=0.0, ge=0.0, le=180.0)
    aimDirection: Vec3DDto = Field(default_factory=lambda: Vec3DDto(x=0.0, y=0.0, z=-1.0))
    luminousFlux: float = Field(default=3600.0, gt=0.0)
    wattage: float = Field(default=40.0, ge=0.0)
    assetId: str
    iesContent: str | None = None


class V2WorkplaneInputDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    height: float = Field(default=0.85, ge=0.0)
    margin: float = Field(default=0.5, ge=0.0)
    pitch: float | None = None
    polygon: list[Point2DDto] | None = None


class V2PhysicsInputDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    maintenanceFactor: float = Field(default=0.8, gt=0.0, le=1.0)
    radiosity: bool = True


class V2ComplianceInputDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    standardId: str | None = "EN 12464-1 (OFFICE)"
    targetLux: float = Field(default=500.0, gt=0.0)
    targetUniformity: float = Field(default=0.6, ge=0.0, le=1.0)
    maxOverdesign: float = Field(default=0.3, ge=0.0)


class V2CalculateRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    polygon: list[Point2DDto] = Field(..., min_length=3)
    ceilingHeight: float = Field(default=3.0, gt=0.0)
    reflectances: SurfaceReflectancesDto = Field(default_factory=SurfaceReflectancesDto)
    fixtures: list[V2FixtureInputDto] = Field(default_factory=list)
    workplane: V2WorkplaneInputDto = Field(default_factory=V2WorkplaneInputDto)
    physics: V2PhysicsInputDto = Field(default_factory=V2PhysicsInputDto)
    compliance: V2ComplianceInputDto | None = None


class V2EvaluationMetricsDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    averageLux: float
    minLux: float
    maxLux: float
    uniformity: float
    minOverMax: float
    totalPowerWatts: float
    powerDensityWPerM2: float
    compliant: bool


class V2EvaluationPointDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    x: float
    y: float
    z: float
    lux: float


class V2IsolineDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    lux: float
    paths: list[list[Point2DDto]]
    label: str | None = None
    compliant: bool | None = None


class V2GridSummaryDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    nx: int
    ny: int
    spacingX: float
    spacingY: float
    wallZone: float
    workPlaneHeight: float


class V2CalculateResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    metrics: V2EvaluationMetricsDto
    grid: V2GridSummaryDto
    points: list[V2EvaluationPointDto]
    matrix: list[list[float]]
    isolines: list[V2IsolineDto]
