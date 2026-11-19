from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class SaveProjectRequestDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True, extra="allow")

    id: str | None = Field(
        default=None,
        description="Optional project ID. If omitted, created; if provided and owned, updated.",
    )
    name: str = Field(description="Project name")
    sceneName: str = Field(default="Scene 01", alias="sceneName", description="Primary scene or active room name")
    roomCount: int = Field(default=1, ge=1, alias="roomCount", description="Number of rooms in project")
    schemaVersion: int = Field(default=2, alias="schemaVersion", description="Project schema version")
    archiveObjectKey: str | None = Field(
        default=None,
        alias="archiveObjectKey",
        description="Object storage key for the packaged .lxsc file",
    )
    thumbnailObjectKey: str | None = Field(
        default=None,
        alias="thumbnailObjectKey",
        description="Object storage key for project preview thumbnail",
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Optional extra client metadata")


class CopyProjectRequestDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    name: str | None = Field(
        default=None,
        description="Optional custom name for the copy. Defaults to 'Copy of {original name}'.",
    )
