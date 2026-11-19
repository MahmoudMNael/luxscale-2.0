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


class SaveProjectRequestDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    schemaVersion: Literal[1] = 1
    id: str | None = Field(default=None, description="Optional project ID. If omitted or not found, a new project is created; if found and owned, it is updated.")
    name: str
    sceneName: str = "Scene 01"
    createdAt: str | None = None
    updatedAt: str | None = None
    room: RoomGeometryDto
    fixtures: list[FixtureInstanceDto] = Field(default_factory=list)
    patterns: list[dict[str, Any]] = Field(default_factory=list)
    workplanes: list[WorkplaneDto] = Field(default_factory=list)
    physics: PhysicsSettingsDto = Field(default_factory=PhysicsSettingsDto)
    compliance: ComplianceCriteriaDto = Field(default_factory=ComplianceCriteriaDto)
    assets: list[PhotometricAssetMetaDto] = Field(default_factory=list)
    results: dict[str, Any] | None = None
    thumbnailObjectKey: str | None = Field(default=None, alias="thumbnailObjectKey")


class CopyProjectRequestDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    name: str | None = Field(
        default=None,
        description="Optional custom name for the copy. Defaults to 'Copy of {original name}'.",
    )
