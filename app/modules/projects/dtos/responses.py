from __future__ import annotations

from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class ProjectDetailResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    name: str
    sceneName: str = Field(default="Scene 01", alias="sceneName")
    roomCount: int = Field(default=1, alias="roomCount")
    schemaVersion: int = Field(default=2, alias="schemaVersion")
    createdAt: str = Field(alias="createdAt")
    updatedAt: str = Field(alias="updatedAt")
    thumbnailObjectKey: str | None = Field(default=None, alias="thumbnailObjectKey")
    thumbnailUrl: str | None = Field(default=None, alias="thumbnailUrl")
    archiveObjectKey: str | None = Field(default=None, alias="archiveObjectKey")
    archiveDownloadUrl: str | None = Field(default=None, alias="archiveDownloadUrl")
    ownerId: str = Field(alias="ownerId")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectListItemDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    id: str
    name: str
    sceneName: str = Field(alias="sceneName")
    roomCount: int = Field(default=1, alias="roomCount")
    schemaVersion: int = Field(alias="schemaVersion")
    createdAt: str = Field(alias="createdAt")
    updatedAt: str = Field(alias="updatedAt")
    thumbnailUrl: str | None = Field(default=None, alias="thumbnailUrl")
    archiveDownloadUrl: str | None = Field(default=None, alias="archiveDownloadUrl")
    ownerId: str = Field(alias="ownerId")


class ProjectPageResponseDto(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    items: list[ProjectListItemDto]
    total: int
    page: int
    limit: int
    totalPages: int = Field(alias="totalPages")
