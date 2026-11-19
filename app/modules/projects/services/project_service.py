from __future__ import annotations

import io
import json
import math
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from fastapi import Depends, HTTPException, status

from app.core.storage.providers.local_provider import LocalStorageProvider
from app.core.storage.providers.s3_provider import S3StorageProvider
from app.core.storage.services.storage_service import StorageService, get_storage_service
from app.modules.projects.dtos.requests import SaveProjectRequestDto
from app.modules.projects.dtos.responses import (
    ProjectDetailResponseDto,
    ProjectListItemDto,
    ProjectPageResponseDto,
)
from app.modules.projects.entities.project_entity import ProjectEntity
from app.modules.projects.models.project_domain import ProjectDomainModel
from app.modules.projects.repositories.project_repository import ProjectRepository, get_project_repository


class ProjectService:
    def __init__(
        self,
        repo: ProjectRepository,
        storage_service: StorageService,
    ) -> None:
        self.repo = repo
        self.storage = storage_service

    def _to_detail_dto(self, entity: ProjectEntity) -> ProjectDetailResponseDto:
        thumb_url = None
        if entity.thumbnail_object_key:
            thumb_url = self.storage.generate_download_url(entity.thumbnail_object_key)

        archive_url = None
        if entity.archive_object_key:
            archive_url = self.storage.generate_download_url(
                entity.archive_object_key,
                filename=f"{entity.name}.lxsc",
            )

        meta = dict(entity.metadata_json)
        return ProjectDetailResponseDto(
            schemaVersion=entity.schema_version,
            id=entity.id,
            name=entity.name,
            sceneName=entity.scene_name,
            createdAt=entity.created_at.isoformat(),
            updatedAt=entity.updated_at.isoformat(),
            room=meta.get("room", {"polygon": [], "ceilingHeight": 3.0, "wallThickness": 0.2}),
            fixtures=meta.get("fixtures", []),
            patterns=meta.get("patterns", []),
            workplanes=meta.get("workplanes", []),
            physics=meta.get("physics", {}),
            compliance=meta.get("compliance", {}),
            assets=meta.get("assets", []),
            results=meta.get("results"),
            thumbnailObjectKey=entity.thumbnail_object_key,
            thumbnailUrl=thumb_url,
            archiveDownloadUrl=archive_url,
            ownerId=str(entity.user_id),
        )

    def _store_archive(self, user_id: uuid.UUID, project_id: str, archive_bytes: bytes) -> str:
        key = f"projects/{user_id}/{project_id}/project.lxsc"
        provider = self.storage.provider
        if isinstance(provider, LocalStorageProvider):
            path = provider._resolve_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive_bytes)
        elif isinstance(provider, S3StorageProvider):
            provider.client.put_object(
                Bucket=provider.bucket,
                Key=key,
                Body=archive_bytes,
                ContentType="application/zip",
            )
        return key

    def _read_archive(self, key: str) -> bytes | None:
        provider = self.storage.provider
        if isinstance(provider, LocalStorageProvider):
            path = provider._resolve_path(key)
            if path.is_file():
                return path.read_bytes()
        elif isinstance(provider, S3StorageProvider):
            try:
                resp = provider.client.get_object(Bucket=provider.bucket, Key=key)
                return resp["Body"].read()
            except Exception:
                return None
        return None

    def save_project(
        self,
        dto: SaveProjectRequestDto,
        user_id: uuid.UUID,
        target_id: str | None = None,
        lxsc_bytes: bytes | None = None,
    ) -> tuple[ProjectDetailResponseDto, bool]:
        """
        Saves or creates project. Returns (dto, is_created).
        Raises 403 Forbidden if project exists and belongs to another user.
        """
        project_id = target_id or dto.id or f"proj_{uuid.uuid4().hex[:12]}"
        existing = self.repo.get_by_id(project_id)

        now = datetime.now(timezone.utc)
        is_created = False

        if existing:
            if existing.user_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied: you do not own project '{project_id}'",
                )
            entity = existing
            entity.name = dto.name
            entity.scene_name = dto.sceneName
            entity.schema_version = dto.schemaVersion
            entity.updated_at = now
            if dto.thumbnailObjectKey is not None:
                entity.thumbnail_object_key = dto.thumbnailObjectKey
        else:
            is_created = True
            created_at = datetime.fromisoformat(dto.createdAt) if dto.createdAt else now
            entity = ProjectEntity(
                id=project_id,
                user_id=user_id,
                name=dto.name,
                scene_name=dto.sceneName,
                schema_version=dto.schemaVersion,
                thumbnail_object_key=dto.thumbnailObjectKey,
                created_at=created_at,
                updated_at=now,
                metadata_json={},
            )

        # Build full document dictionary
        doc_dict = dto.model_dump(by_alias=True)
        doc_dict["id"] = project_id
        doc_dict["name"] = entity.name
        doc_dict["sceneName"] = entity.scene_name
        doc_dict["createdAt"] = entity.created_at.isoformat()
        doc_dict["updatedAt"] = entity.updated_at.isoformat()
        entity.metadata_json = doc_dict

        # Package .lxsc archive
        if not lxsc_bytes:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project.json", json.dumps(doc_dict, indent=2))
            lxsc_bytes = buf.getvalue()

        # Save archive into object storage
        archive_key = self._store_archive(user_id, project_id, lxsc_bytes)
        entity.archive_object_key = archive_key

        saved = self.repo.save(entity)
        return self._to_detail_dto(saved), is_created

    def copy_project(
        self,
        source_id: str,
        user_id: uuid.UUID,
        custom_name: str | None = None,
    ) -> ProjectDetailResponseDto:
        existing = self.repo.get_by_id(source_id)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{source_id}' not found",
            )
        if existing.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: you do not own project '{source_id}'",
            )

        copy_name = custom_name.strip() if custom_name and custom_name.strip() else f"Copy of {existing.name}"
        copy_id = f"proj_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc)

        # Duplicate archive in storage
        new_archive_key = f"projects/{user_id}/{copy_id}/project.lxsc"
        archive_copied = False
        if existing.archive_object_key:
            archive_copied = self.storage.copy_object(existing.archive_object_key, new_archive_key)

        if not archive_copied:
            # Fallback: re-archive from metadata
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project.json", json.dumps(existing.metadata_json, indent=2))
            new_archive_key = self._store_archive(user_id, copy_id, buf.getvalue())

        # Copy metadata
        copy_meta = dict(existing.metadata_json)
        copy_meta["id"] = copy_id
        copy_meta["name"] = copy_name
        copy_meta["createdAt"] = now.isoformat()
        copy_meta["updatedAt"] = now.isoformat()

        copy_entity = ProjectEntity(
            id=copy_id,
            user_id=user_id,
            name=copy_name,
            scene_name=existing.scene_name,
            schema_version=existing.schema_version,
            thumbnail_object_key=existing.thumbnail_object_key,
            archive_object_key=new_archive_key,
            created_at=now,
            updated_at=now,
            metadata_json=copy_meta,
        )

        saved = self.repo.save(copy_entity)
        return self._to_detail_dto(saved)

    def get_project(self, project_id: str, user_id: uuid.UUID) -> ProjectDetailResponseDto:
        entity = self.repo.get_by_id(project_id)
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )
        if entity.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: you do not own project '{project_id}'",
            )
        return self._to_detail_dto(entity)

    def list_projects(
        self,
        user_id: uuid.UUID,
        query: str | None = None,
        sort_by: str = "updatedAt",
        sort_order: str = "desc",
        page: int = 1,
        limit: int = 20,
    ) -> ProjectPageResponseDto:
        offset = max(0, (page - 1) * limit)
        total = self.repo.count_by_user(user_id, query=query)
        entities = self.repo.list_by_user(
            user_id,
            query=query,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )
        total_pages = math.ceil(total / limit) if total > 0 else 0
        items: list[ProjectListItemDto] = []
        for e in entities:
            domain = ProjectDomainModel.from_dict(e.metadata_json, user_id=e.user_id)
            thumb_url = None
            if e.thumbnail_object_key:
                thumb_url = self.storage.generate_download_url(e.thumbnail_object_key)
            items.append(
                ProjectListItemDto(
                    id=e.id,
                    name=e.name,
                    sceneName=e.scene_name,
                    schemaVersion=e.schema_version,
                    createdAt=e.created_at.isoformat(),
                    updatedAt=e.updated_at.isoformat(),
                    fixtureCount=len(domain.fixtures_data),
                    roomArea=domain.compute_room_area(),
                    thumbnailUrl=thumb_url,
                    ownerId=str(e.user_id),
                )
            )
        return ProjectPageResponseDto(
            items=items,
            total=total,
            page=page,
            limit=limit,
            totalPages=total_pages,
        )

    def export_lxsc(self, project_id: str, user_id: uuid.UUID) -> tuple[str, bytes]:
        entity = self.repo.get_by_id(project_id)
        if not entity:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Project '{project_id}' not found",
            )
        if entity.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: you do not own project '{project_id}'",
            )

        lxsc_bytes = None
        if entity.archive_object_key:
            lxsc_bytes = self._read_archive(entity.archive_object_key)

        if not lxsc_bytes and entity.file_path:
            p = Path(entity.file_path)
            if p.is_file():
                lxsc_bytes = p.read_bytes()

        if not lxsc_bytes:
            # Fallback: bundle from metadata
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("project.json", json.dumps(entity.metadata_json, indent=2))
            lxsc_bytes = buf.getvalue()

        return f"{entity.name or project_id}.lxsc", lxsc_bytes

    def import_lxsc(self, lxsc_bytes: bytes, user_id: uuid.UUID) -> ProjectDetailResponseDto:
        buf = io.BytesIO(lxsc_bytes)
        with zipfile.ZipFile(buf, "r") as zf:
            if "project.json" not in zf.namelist():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid .lxsc archive: project.json missing from root of archive",
                )
            raw_text = zf.read("project.json").decode("utf-8")
            data = json.loads(raw_text)

        dto = SaveProjectRequestDto.model_validate(data)
        saved_dto, _ = self.save_project(dto, user_id, lxsc_bytes=lxsc_bytes)
        return saved_dto

    def delete_project(self, project_id: str, user_id: uuid.UUID) -> bool:
        entity = self.repo.get_by_id(project_id)
        if not entity:
            return False
        if entity.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: you do not own project '{project_id}'",
            )
        if entity.archive_object_key:
            self.storage.delete_object(entity.archive_object_key)
        return self.repo.delete(project_id, user_id)


def get_project_service(
    repo: ProjectRepository = Depends(get_project_repository),
    storage_service: StorageService = Depends(get_storage_service),
) -> ProjectService:
    return ProjectService(repo, storage_service)
