from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from fastapi import Depends

from app.modules.projects.models import ProjectDomainModel, ProjectSummary
from app.modules.projects.entities import ProjectEntity
from app.modules.projects.repository import ProjectRepository, get_project_repository

STORAGE_DIR = Path(__file__).resolve().parents[3] / "storage" / "projects"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class ProjectService:
    def __init__(self, repo: ProjectRepository) -> None:
        self.repo = repo

    def save_project(
        self,
        domain_model: ProjectDomainModel,
        lxsc_bytes: bytes | None = None,
    ) -> ProjectDomainModel:
        file_path = STORAGE_DIR / f"{domain_model.id}.lxsc"

        if lxsc_bytes:
            file_path.write_bytes(lxsc_bytes)
        else:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project.json", json.dumps(domain_model.to_dict(), indent=2))
            file_path.write_bytes(buf.getvalue())

        now = datetime.now(timezone.utc)
        entity = ProjectEntity(
            id=domain_model.id,
            name=domain_model.name,
            scene_name=domain_model.scene_name,
            schema_version=domain_model.schema_version,
            file_path=str(file_path),
            created_at=datetime.fromisoformat(domain_model.created_at)
            if domain_model.created_at
            else now,
            updated_at=now,
            metadata_json=domain_model.to_dict(),
        )

        saved_entity = self.repo.save(entity)
        return ProjectDomainModel.from_dict(saved_entity.metadata_json, saved_entity.file_path)

    def get_project(self, project_id: str) -> tuple[ProjectDomainModel | None, bytes | None]:
        entity = self.repo.get_by_id(project_id)
        if not entity:
            return None, None
        model = ProjectDomainModel.from_dict(entity.metadata_json, entity.file_path)
        lxsc_bytes = None
        if entity.file_path:
            p = Path(entity.file_path)
            if p.exists():
                lxsc_bytes = p.read_bytes()
        return model, lxsc_bytes

    def list_projects(self) -> list[ProjectSummary]:
        entities = self.repo.list_all()
        summaries: list[ProjectSummary] = []
        for e in entities:
            model = ProjectDomainModel.from_dict(e.metadata_json, e.file_path)
            summaries.append(model.to_summary())
        return summaries

    def export_lxsc(self, project_id: str) -> tuple[str, bytes]:
        model, lxsc_bytes = self.get_project(project_id)
        if not model or not lxsc_bytes:
            raise FileNotFoundError(f"Project archive for '{project_id}' not found")
        filename = f"{model.name or project_id}.lxsc"
        return filename, lxsc_bytes

    def import_lxsc(self, lxsc_bytes: bytes) -> ProjectDomainModel:
        buf = io.BytesIO(lxsc_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            if "project.json" not in zf.namelist():
                raise ValueError("Invalid .lxsc archive: project.json missing from root of archive")
            raw_text = zf.read("project.json").decode("utf-8")
            data = json.loads(raw_text)

        domain_model = ProjectDomainModel.from_dict(data)
        return self.save_project(domain_model, lxsc_bytes)

    def delete_project(self, project_id: str) -> bool:
        entity = self.repo.get_by_id(project_id)
        if not entity:
            return False
        if entity.file_path:
            p = Path(entity.file_path)
            if p.exists():
                p.unlink()
        return self.repo.delete(project_id)


def get_project_service(
    repo: ProjectRepository = Depends(get_project_repository),
) -> ProjectService:
    return ProjectService(repo)
