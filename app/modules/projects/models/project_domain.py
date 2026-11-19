from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ProjectSummary:
    id: str
    name: str
    scene_name: str
    room_count: int
    schema_version: int
    created_at: str
    updated_at: str
    owner_id: str | None = None
    thumbnail_url: str | None = None
    archive_download_url: str | None = None


@dataclass(frozen=True)
class ProjectDomainModel:
    id: str
    name: str
    scene_name: str
    room_count: int
    schema_version: int
    created_at: str
    updated_at: str
    user_id: uuid.UUID | None = None
    thumbnail_object_key: str | None = None
    archive_object_key: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        user_id: uuid.UUID | None = None,
        thumbnail_object_key: str | None = None,
        archive_object_key: str | None = None,
    ) -> ProjectDomainModel:
        now_iso = datetime.now(timezone.utc).isoformat()
        return cls(
            id=data.get("id") or f"proj_{uuid.uuid4().hex[:12]}",
            name=data.get("name", "Untitled Project"),
            scene_name=data.get("sceneName", data.get("scene_name", "Scene 01")),
            room_count=int(data.get("roomCount", data.get("room_count", 1))),
            schema_version=int(data.get("schemaVersion", data.get("schema_version", 2))),
            created_at=data.get("createdAt", data.get("created_at", now_iso)),
            updated_at=data.get("updatedAt", data.get("updated_at", now_iso)),
            user_id=user_id,
            thumbnail_object_key=thumbnail_object_key or data.get("thumbnailObjectKey"),
            archive_object_key=archive_object_key or data.get("archiveObjectKey"),
            metadata=data.get("metadata", {}),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "sceneName": self.scene_name,
            "roomCount": self.room_count,
            "schemaVersion": self.schema_version,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "thumbnailObjectKey": self.thumbnail_object_key,
            "archiveObjectKey": self.archive_object_key,
            "metadata": self.metadata,
        }
