from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class ProjectSummary:
    id: str
    name: str
    scene_name: str
    schema_version: int
    created_at: str
    updated_at: str
    fixture_count: int
    room_area: float


@dataclass(frozen=True)
class ProjectDomainModel:
    id: str
    name: str
    scene_name: str
    schema_version: int
    created_at: str
    updated_at: str
    room_data: dict[str, Any]
    fixtures_data: list[dict[str, Any]]
    patterns_data: list[dict[str, Any]]
    workplanes_data: list[dict[str, Any]]
    physics_data: dict[str, Any]
    compliance_data: dict[str, Any]
    assets_data: list[dict[str, Any]]
    results_data: dict[str, Any] | None = None
    file_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], file_path: str | None = None) -> ProjectDomainModel:
        now_iso = datetime.now(timezone.utc).isoformat()
        return cls(
            id=data["id"],
            name=data["name"],
            scene_name=data.get("sceneName", "Scene 01"),
            schema_version=data.get("schemaVersion", 1),
            created_at=data.get("createdAt", now_iso),
            updated_at=data.get("updatedAt", now_iso),
            room_data=data.get("room", {}),
            fixtures_data=data.get("fixtures", []),
            patterns_data=data.get("patterns", []),
            workplanes_data=data.get("workplanes", []),
            physics_data=data.get("physics", {}),
            compliance_data=data.get("compliance", {}),
            assets_data=data.get("assets", []),
            results_data=data.get("results"),
            file_path=file_path,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "id": self.id,
            "name": self.name,
            "sceneName": self.scene_name,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "room": self.room_data,
            "fixtures": self.fixtures_data,
            "patterns": self.patterns_data,
            "workplanes": self.workplanes_data,
            "physics": self.physics_data,
            "compliance": self.compliance_data,
            "assets": self.assets_data,
            "results": self.results_data,
        }

    def compute_room_area(self) -> float:
        poly = self.room_data.get("polygon", [])
        if len(poly) < 3:
            return 0.0
        area = 0.0
        for i in range(len(poly)):
            j = (i + 1) % len(poly)
            p1 = poly[i]
            p2 = poly[j]
            area += p1["x"] * p2["y"] - p2["x"] * p1["y"]
        return round(abs(area) * 0.5, 2)

    def to_summary(self) -> ProjectSummary:
        return ProjectSummary(
            id=self.id,
            name=self.name,
            scene_name=self.scene_name,
            schema_version=self.schema_version,
            created_at=self.created_at,
            updated_at=self.updated_at,
            fixture_count=len(self.fixtures_data),
            room_area=self.compute_room_area(),
        )
