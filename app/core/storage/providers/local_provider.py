from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from app.core.storage.interface import ObjectStorageProvider

DEFAULT_STORAGE_ROOT = Path(__file__).resolve().parents[4] / "storage" / "objects"


class LocalStorageProvider(ObjectStorageProvider):
    """Local filesystem object storage with HMAC-signed direct PUT/GET endpoints."""

    def __init__(
        self,
        base_dir: Path | str | None = None,
        base_url: str | None = None,
        secret: str | None = None,
    ) -> None:
        self.root = Path(base_dir or os.getenv("STORAGE_LOCAL_DIR", DEFAULT_STORAGE_ROOT)).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.base_url = (base_url or os.getenv("STORAGE_BASE_URL", "")).rstrip("/")
        self.secret = (secret or os.getenv("STORAGE_LOCAL_SECRET", "luxscale-local-storage-secret")).encode("utf-8")

    def _resolve_path(self, key: str) -> Path:
        clean_key = key.lstrip("/").replace("\\", "/")
        full_path = (self.root / clean_key).resolve()
        if not str(full_path).startswith(str(self.root)):
            raise ValueError(f"Path traversal detected: {key}")
        return full_path

    def _create_token(self, payload: dict[str, Any]) -> str:
        raw_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        b64_payload = base64.urlsafe_b64encode(raw_json).decode("ascii").rstrip("=")
        sig = hmac.new(self.secret, b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
        return f"{b64_payload}.{sig}"

    def verify_token(self, token: str, expected_action: str | None = None) -> dict[str, Any] | None:
        parts = token.split(".", 1)
        if len(parts) != 2:
            return None
        b64_payload, sig = parts
        expected_sig = hmac.new(self.secret, b64_payload.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        try:
            # Fix base64 padding
            padding = 4 - (len(b64_payload) % 4)
            if padding and padding != 4:
                b64_payload += "=" * padding
            payload = json.loads(base64.urlsafe_b64decode(b64_payload).decode("utf-8"))
        except Exception:
            return None

        exp = payload.get("exp", 0)
        if time.time() > exp:
            return None

        if expected_action and payload.get("act") != expected_action:
            return None

        return payload

    def generate_upload_url(
        self,
        key: str,
        content_type: str,
        expires_in: int = 3600,
    ) -> dict[str, Any]:
        exp = int(time.time()) + expires_in
        token = self._create_token({
            "k": key,
            "ct": content_type,
            "exp": exp,
            "act": "put",
        })
        upload_url = f"{self.base_url}/api/v2/storage/raw/{token}"
        download_url = self.generate_download_url(key, expires_in=expires_in)
        return {
            "upload_url": upload_url,
            "method": "PUT",
            "headers": {"Content-Type": content_type},
            "file_key": key,
            "download_url": download_url,
        }

    def generate_download_url(
        self,
        key: str,
        expires_in: int = 3600,
        filename: str | None = None,
    ) -> str:
        exp = int(time.time()) + expires_in
        payload: dict[str, Any] = {
            "k": key,
            "exp": exp,
            "act": "get",
        }
        if filename:
            payload["fn"] = filename
        token = self._create_token(payload)
        return f"{self.base_url}/api/v2/storage/raw/{token}"

    def copy_object(self, source_key: str, dest_key: str) -> bool:
        src_path = self._resolve_path(source_key)
        if not src_path.is_file():
            return False
        dst_path = self._resolve_path(dest_key)
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        return True

    def delete_object(self, key: str) -> bool:
        path = self._resolve_path(key)
        if path.is_file():
            path.unlink()
            return True
        return False

    def object_exists(self, key: str) -> bool:
        return self._resolve_path(key).is_file()
