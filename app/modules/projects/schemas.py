from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


class Point2DDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    x: float
    y: float


class Vec3DDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    x: float
    y: float
    z: float


class ObstructionDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    id: str
    name: str = "Obstruction"
    polygon: list[Point2DDto]
    height: float = 3.0
    reflectance: float = 0.5


class SurfaceReflectancesDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    ceiling: float = Field(default=0.7, ge=0.0, le=1.0)
    walls: float = Field(default=0.5, ge=0.0, le=1.0)
    floor: float = Field(default=0.2, ge=0.0, le=1.0)


class RoomGeometryDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    polygon: list[Point2DDto]
    ceilingHeight: float = Field(default=3.0, gt=0.0)
    wallThickness: float = Field(default=0.2, ge=0.0)
    reflectances: SurfaceReflectancesDto = Field(default_factory=SurfaceReflectancesDto)
    obstructions: list[ObstructionDto] = Field(default_factory=list)


class FixtureInstanceDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    id: str
    name: str = "Fixture"
    assetId: str
    position: Vec3DDto
    rotation: float = Field(default=0.0, ge=0.0, le=360.0)
    tiltAngle: float = Field(default=0.0, ge=0.0, le=180.0)
    aimVector: Vec3DDto = Field(default_factory=lambda: Vec3DDto(x=0.0, y=0.0, z=-1.0))
    luminousFlux: float = Field(default=3600.0, gt=0.0)
    wattage: float = Field(default=40.0, ge=0.0)
    cct: int = Field(default=4000, ge=1000, le=15000)
    fluxMultiplier: float = Field(default=1.0, ge=0.0, le=1.0)
    patternId: str | None = None


class WorkplaneDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    id: str = "WP-01"
    name: str = "Standard Task Plane"
    height: float = Field(default=0.85, ge=0.0)
    margin: float = Field(default=0.5, ge=0.0)
    pitch: float | None = None
    polygon: list[Point2DDto] | None = None


class PhysicsSettingsDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    maintenanceFactor: float = Field(default=0.8, gt=0.0, le=1.0)
    radiosity: bool = True


class ComplianceCriteriaDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    standardId: str | None = "EN 12464-1 (OFFICE)"
    targetLux: float = Field(default=500.0, gt=0.0)
    targetUniformity: float = Field(default=0.6, ge=0.0, le=1.0)
    maxOverdesign: float = Field(default=0.3, ge=0.0)


class PhotometricAssetMetaDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    id: str
    fileName: str
    format: Literal["ies", "ldt"] = "ies"
    luminaireName: str = "Luminaire"
    lumens: float = 3600.0
    wattage: float = 40.0
    beamAngleH: float = 110.0
    beamAngleV: float = 110.0
    maxCandela: float = 1000.0


class ProjectDocumentDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    schemaVersion: Literal[1] = 1
    id: str
    name: str
    sceneName: str = "Scene 01"
    createdAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updatedAt: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    room: RoomGeometryDto
    fixtures: list[FixtureInstanceDto] = Field(default_factory=list)
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    workplanes: list[WorkplaneDto] = Field(default_factory=list)
    physics: PhysicsSettingsDto = Field(default_factory=PhysicsSettingsDto)
    compliance: ComplianceCriteriaDto = Field(default_factory=ComplianceCriteriaDto)
    assets: list[PhotometricAssetMetaDto] = Field(default_factory=list)
    results: dict[str, Any] | None = None


class ProjectListItemDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)
    id: str
    name: str
    sceneName: str
    schemaVersion: int
    createdAt: str
    updatedAt: str
    fixtureCount: int = 0
    roomArea: float = 0.0
