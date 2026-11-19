from __future__ import annotations

import os
from typing import Any

from app.core.storage.interface import ObjectStorageProvider


class S3StorageProvider(ObjectStorageProvider):
    """S3-compatible object storage provider supporting AWS S3, Cloudflare R2, and MinIO."""

    def __init__(
        self,
        bucket_name: str | None = None,
        endpoint_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        region_name: str | None = None,
        public_domain: str | None = None,
    ) -> None:
        self.bucket = bucket_name or os.getenv("S3_BUCKET_NAME", "luxscale")
        self.endpoint_url = endpoint_url or os.getenv("S3_ENDPOINT_URL")
        self.access_key_id = access_key_id or os.getenv("S3_ACCESS_KEY_ID") or os.getenv("AWS_ACCESS_KEY_ID")
        self.secret_access_key = secret_access_key or os.getenv("S3_SECRET_ACCESS_KEY") or os.getenv("AWS_SECRET_ACCESS_KEY")
        self.region_name = region_name or os.getenv("S3_REGION_NAME", "auto")
        self.public_domain = (public_domain or os.getenv("S3_PUBLIC_DOMAIN", "")).rstrip("/")

        self._client = None

    @property
    def client(self) -> Any:
        if self._client is None:
            import boto3
            from botocore.config import Config

            cfg = Config(signature_version="s3v4")
            self._client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key_id,
                aws_secret_access_key=self.secret_access_key,
                region_name=self.region_name,
                config=cfg,
            )
        return self._client

    def generate_upload_url(
        self,
        key: str,
        content_type: str,
        expires_in: int = 3600,
    ) -> dict[str, Any]:
        clean_key = key.lstrip("/")
        upload_url = self.client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self.bucket,
                "Key": clean_key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
        download_url = self.generate_download_url(clean_key, expires_in=expires_in)
        return {
            "upload_url": upload_url,
            "method": "PUT",
            "headers": {"Content-Type": content_type},
            "file_key": clean_key,
            "download_url": download_url,
        }

    def generate_download_url(
        self,
        key: str,
        expires_in: int = 3600,
        filename: str | None = None,
    ) -> str:
        clean_key = key.lstrip("/")
        if self.public_domain:
            return f"{self.public_domain}/{clean_key}"

        params: dict[str, Any] = {
            "Bucket": self.bucket,
            "Key": clean_key,
        }
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'

        return self.client.generate_presigned_url(
            "get_object",
            Params=params,
            ExpiresIn=expires_in,
        )

    def copy_object(self, source_key: str, dest_key: str) -> bool:
        clean_src = source_key.lstrip("/")
        clean_dst = dest_key.lstrip("/")
        try:
            self.client.copy_object(
                Bucket=self.bucket,
                CopySource={"Bucket": self.bucket, "Key": clean_src},
                Key=clean_dst,
            )
            return True
        except Exception:
            return False

    def delete_object(self, key: str) -> bool:
        clean_key = key.lstrip("/")
        try:
            self.client.delete_object(Bucket=self.bucket, Key=clean_key)
            return True
        except Exception:
            return False

    def object_exists(self, key: str) -> bool:
        clean_key = key.lstrip("/")
        try:
            self.client.head_object(Bucket=self.bucket, Key=clean_key)
            return True
        except Exception:
            return False
