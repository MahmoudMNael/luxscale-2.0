from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

from app.modules.projects.schemas import (
    ComplianceCriteriaDto,
    FixtureInstanceDto,
    PhotometricAssetMetaDto,
    PhysicsSettingsDto,
    RoomGeometryDto,
    WorkplaneDto,
)


class ProjectDetailResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schemaVersion: Literal[1] = 1
    id: str
    name: str
    sceneName: str = "Scene 01"
    createdAt: str
    updatedAt: str
    room: RoomGeometryDto
    fixtures: list[FixtureInstanceDto] = Field(default_factory=list)
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    workplanes: list[WorkplaneDto] = Field(default_factory=list)
    physics: PhysicsSettingsDto = Field(default_factory=PhysicsSettingsDto)
    compliance: ComplianceCriteriaDto = Field(default_factory=ComplianceCriteriaDto)
    assets: list[PhotometricAssetMetaDto] = Field(default_factory=list)
    results: dict[str, Any] | None = None
    thumbnailObjectKey: str | None = Field(default=None, alias="thumbnailObjectKey")
    thumbnailUrl: str | None = Field(default=None, alias="thumbnailUrl")
    archiveDownloadUrl: str | None = Field(default=None, alias="archiveDownloadUrl")
    ownerId: str = Field(alias="ownerId")


class ProjectListItemDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    name: str
    sceneName: str = Field(alias="sceneName")
    schemaVersion: int = Field(alias="schemaVersion")
    createdAt: str = Field(alias="createdAt")
    updatedAt: str = Field(alias="updatedAt")
    fixtureCount: int = Field(default=0, alias="fixtureCount")
    roomArea: float = Field(default=0.0, alias="roomArea")
    thumbnailUrl: str | None = Field(default=None, alias="thumbnailUrl")
    ownerId: str = Field(alias="ownerId")
