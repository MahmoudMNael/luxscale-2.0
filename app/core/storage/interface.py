from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ObjectStorageProvider(Protocol):
    """Abstract protocol for swappable cloud/local object storage."""

    def generate_upload_url(
        self,
        key: str,
        content_type: str,
        expires_in: int = 3600,
    ) -> dict[str, Any]:
        """Generate a presigned or signed URL for browser direct PUT upload."""
        ...

    def generate_download_url(
        self,
        key: str,
        expires_in: int = 3600,
        filename: str | None = None,
    ) -> str:
        """Generate a presigned or signed URL for browser direct GET download."""
        ...

    def copy_object(self, source_key: str, dest_key: str) -> bool:
        """Copy an object inside the storage bucket/filesystem."""
        ...

    def delete_object(self, key: str) -> bool:
        """Delete an object from storage."""
        ...

    def object_exists(self, key: str) -> bool:
        """Check if an object exists in storage."""
        ...
