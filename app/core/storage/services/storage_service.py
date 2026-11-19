from __future__ import annotations

import os
import uuid
from functools import lru_cache
from pathlib import Path

from app.core.storage.dtos.requests import UploadTicketRequestDto
from app.core.storage.dtos.responses import UploadTicketResponseDto
from app.core.storage.interface import ObjectStorageProvider
from app.core.storage.providers.local_provider import LocalStorageProvider
from app.core.storage.providers.s3_provider import S3StorageProvider


class StorageService:
    """High-level storage service that scopes keys and delegates to swappable providers."""

    def __init__(self, provider: ObjectStorageProvider | None = None) -> None:
        self.provider = provider or self._init_provider_from_env()

    @staticmethod
    def _init_provider_from_env() -> ObjectStorageProvider:
        backend = os.getenv("STORAGE_BACKEND", "local").lower().strip()
        if backend == "s3" or backend == "r2":
            return S3StorageProvider()
        return LocalStorageProvider()

    def resolve_object_key(
        self,
        purpose: str,
        user_id: str | None = None,
        filename: str | None = None,
        project_id: str | None = None,
    ) -> str:
        safe_user = str(user_id or "anonymous").strip()
        ext = ""
        clean_name = "asset"
        if filename:
            p = Path(filename)
            ext = p.suffix
            clean_name = p.stem.replace(" ", "_")[:64]

        unique_id = uuid.uuid4().hex[:12]

        if purpose == "project_thumbnail":
            proj = project_id or "shared"
            return f"thumbnails/{safe_user}/{proj}/{clean_name}_{unique_id}{ext or '.png'}"
        elif purpose == "project_archive":
            proj = project_id or unique_id
            return f"projects/{safe_user}/{proj}/project.lxsc"
        elif purpose == "signature_logo":
            return f"signatures/{safe_user}/logo_{unique_id}{ext or '.png'}"
        else:
            return f"uploads/{safe_user}/{clean_name}_{unique_id}{ext}"

    def create_upload_ticket(
        self,
        request: UploadTicketRequestDto,
        user_id: str | None = None,
        expires_in: int = 3600,
    ) -> UploadTicketResponseDto:
        file_key = self.resolve_object_key(
            purpose=request.purpose,
            user_id=user_id,
            filename=request.filename,
            project_id=request.projectId,
        )
        res = self.provider.generate_upload_url(
            key=file_key,
            content_type=request.contentType,
            expires_in=expires_in,
        )
        return UploadTicketResponseDto(
            uploadUrl=res["upload_url"],
            method=res.get("method", "PUT"),
            fileKey=res["file_key"],
            downloadUrl=res["download_url"],
            headers=res.get("headers", {}),
        )

    def generate_download_url(
        self,
        key: str,
        expires_in: int = 3600,
        filename: str | None = None,
    ) -> str:
        return self.provider.generate_download_url(
            key=key,
            expires_in=expires_in,
            filename=filename,
        )

    def copy_object(self, source_key: str, dest_key: str) -> bool:
        return self.provider.copy_object(source_key, dest_key)

    def delete_object(self, key: str) -> bool:
        return self.provider.delete_object(key)

    def object_exists(self, key: str) -> bool:
        return self.provider.object_exists(key)


@lru_cache(maxsize=1)
def get_storage_service() -> StorageService:
    return StorageService()
