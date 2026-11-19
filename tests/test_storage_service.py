from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.storage.interface import ObjectStorageProvider
from app.core.storage.dtos.requests import UploadTicketRequestDto
from app.core.storage.providers.local_provider import LocalStorageProvider
from app.core.storage.providers.s3_provider import S3StorageProvider
from app.core.storage.services.storage_service import StorageService, get_storage_service


@pytest.fixture
def temp_storage(tmp_path: Path) -> LocalStorageProvider:
    return LocalStorageProvider(base_dir=tmp_path, base_url="http://testserver", secret="test-secret")


def test_local_provider_token_and_urls(temp_storage: LocalStorageProvider) -> None:
    res = temp_storage.generate_upload_url("thumbnails/user1/test.png", "image/png", expires_in=100)
    assert res["method"] == "PUT"
    assert "thumbnails/user1/test.png" == res["file_key"]
    assert res["upload_url"].startswith("http://testserver/api/v2/storage/raw/")
    assert res["download_url"].startswith("http://testserver/api/v2/storage/raw/")

    # Extract token
    token = res["upload_url"].split("/raw/")[1]
    payload = temp_storage.verify_token(token, expected_action="put")
    assert payload is not None
    assert payload["k"] == "thumbnails/user1/test.png"
    assert payload["ct"] == "image/png"
    assert payload["act"] == "put"

    # Action mismatch check
    assert temp_storage.verify_token(token, expected_action="get") is None

    # Tampered token check
    tampered = token[:-4] + "abcd"
    assert temp_storage.verify_token(tampered) is None


def test_local_provider_file_ops(temp_storage: LocalStorageProvider) -> None:
    # Write directly to disk
    target = temp_storage._resolve_path("projects/user1/p1/project.lxsc")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"hello lxsc")

    assert temp_storage.object_exists("projects/user1/p1/project.lxsc") is True
    assert temp_storage.object_exists("nonexistent.txt") is False

    # Copy
    copied = temp_storage.copy_object("projects/user1/p1/project.lxsc", "projects/user1/p2/project.lxsc")
    assert copied is True
    assert temp_storage.object_exists("projects/user1/p2/project.lxsc") is True
    assert temp_storage._resolve_path("projects/user1/p2/project.lxsc").read_bytes() == b"hello lxsc"

    # Delete
    deleted = temp_storage.delete_object("projects/user1/p1/project.lxsc")
    assert deleted is True
    assert temp_storage.object_exists("projects/user1/p1/project.lxsc") is False


def test_local_provider_path_traversal(temp_storage: LocalStorageProvider) -> None:
    with pytest.raises(ValueError, match="Path traversal detected"):
        temp_storage._resolve_path("../../etc/passwd")


def test_s3_provider_mocked() -> None:
    with patch("boto3.client") as mock_boto:
        mock_s3 = MagicMock()
        mock_boto.return_value = mock_s3
        mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/key?signed=true"

        provider = S3StorageProvider(bucket_name="test-bucket", public_domain="https://cdn.example.com")
        res = provider.generate_upload_url("thumbnails/pic.png", "image/png")
        assert res["upload_url"] == "https://s3.amazonaws.com/test-bucket/key?signed=true"
        assert res["file_key"] == "thumbnails/pic.png"
        assert res["download_url"] == "https://cdn.example.com/thumbnails/pic.png"

        provider.copy_object("src.png", "dst.png")
        mock_s3.copy_object.assert_called_once_with(
            Bucket="test-bucket",
            CopySource={"Bucket": "test-bucket", "Key": "src.png"},
            Key="dst.png",
        )

        provider.delete_object("dst.png")
        mock_s3.delete_object.assert_called_once_with(Bucket="test-bucket", Key="dst.png")


def test_storage_service_key_scoping() -> None:
    service = StorageService(provider=MagicMock(spec=ObjectStorageProvider))
    k1 = service.resolve_object_key("project_thumbnail", user_id="u1", filename="my image.png", project_id="p123")
    assert k1.startswith("thumbnails/u1/p123/my_image_")
    assert k1.endswith(".png")

    k2 = service.resolve_object_key("project_archive", user_id="u1", project_id="p123")
    assert k2 == "projects/u1/p123/project.lxsc"

    k3 = service.resolve_object_key("signature_logo", user_id="u1", filename="logo.jpg")
    assert k3.startswith("signatures/u1/logo_")
    assert k3.endswith(".jpg")


def test_storage_api_flow(tmp_path: Path) -> None:
    test_provider = LocalStorageProvider(base_dir=tmp_path, base_url="", secret="api-secret")
    test_service = StorageService(provider=test_provider)

    app.dependency_overrides[get_storage_service] = lambda: test_service
    client = TestClient(app)

    try:
        # 1. Request upload ticket
        req_payload = {
            "purpose": "signature_logo",
            "contentType": "image/png",
            "filename": "firm_logo.png",
        }
        resp = client.post("/api/v2/storage/upload-ticket", json=req_payload)
        assert resp.status_code == 200
        ticket = resp.json()
        assert "uploadUrl" in ticket
        assert "downloadUrl" in ticket
        assert "fileKey" in ticket
        assert ticket["fileKey"].startswith("signatures/anonymous/logo_")

        upload_path = ticket["uploadUrl"]
        download_path = ticket["downloadUrl"]

        # 2. Upload raw binary via PUT
        file_bytes = b"\x89PNG\r\n\x1a\nfake-png-binary-content"
        put_resp = client.put(
            upload_path,
            content=file_bytes,
            headers={"Content-Type": "image/png"},
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["status"] == "uploaded"

        # 3. Download raw binary via GET
        get_resp = client.get(download_path)
        assert get_resp.status_code == 200
        assert get_resp.content == file_bytes
        assert get_resp.headers["content-type"] == "image/png"

        # 4. Tampered PUT fails with 403
        bad_put = client.put("/api/v2/storage/raw/invalid.token", content=b"fail")
        assert bad_put.status_code == 403

        # 5. Tampered GET fails with 403
        bad_get = client.get("/api/v2/storage/raw/invalid.token")
        assert bad_get.status_code == 403
    finally:
        app.dependency_overrides.clear()
