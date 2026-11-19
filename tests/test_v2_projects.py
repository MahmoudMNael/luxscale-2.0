from __future__ import annotations

import io
import zipfile
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.db.base import Base
from app.core.db.session import get_db
from app.core.storage.providers.local_provider import LocalStorageProvider
from app.core.storage.services.storage_service import StorageService, get_storage_service
from app.modules.auth.services.auth_service import AuthService, get_auth_service
from app.modules.auth.repositories.account_repository import AccountRepository
from app.modules.photometry.ldt_service import load_ldt
from app.modules.users.entities.user_entity import UserEntity
from app.modules.users.repositories.user_repository import UserRepository

SAMPLE_LDT = """Company XYZ
1
1
1
0
5
0
Rep-001
Troffer 600
Lum-001
troffer.ldt
2026-10-11
600
600
80
600
600
80
80
80
80
100
100
1.0
0
1
1
LED
3600
4000
80
40
0 0 0 0 0 0 0 0 0 0
0
0 30 60 75 90
280 240 150 50 0
"""


@pytest.fixture
def test_setup(tmp_path: Path):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSession()

    user_repo = UserRepository(db)
    account_repo = AccountRepository(db)
    auth_service = AuthService(user_repo, account_repo)
    auth_service.auth_secret_key = "test-secret-key-12345678901234567890"

    storage_provider = LocalStorageProvider(base_dir=tmp_path, base_url="http://storage.local", secret="test-sec")
    storage_service = StorageService(provider=storage_provider)

    # Create two test users for ownership testing
    user_a = UserEntity(email="user_a@lxscale.com", name="User A", role="user")
    user_a = user_repo.save(user_a)

    user_b = UserEntity(email="user_b@lxscale.com", name="User B", role="user")
    user_b = user_repo.save(user_b)

    token_a, _ = auth_service.mint_product_access_token(user_a)
    token_b, _ = auth_service.mint_product_access_token(user_b)

    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_storage_service] = lambda: storage_service

    yield {
        "db": db,
        "user_a": user_a,
        "user_b": user_b,
        "token_a": token_a,
        "token_b": token_b,
        "storage": storage_service,
    }

    app.dependency_overrides.clear()
    db.close()


def test_ldt_parser() -> None:
    profile = load_ldt(SAMPLE_LDT)
    assert profile is not None
    assert profile.vertical_angles == [0.0, 30.0, 60.0, 75.0, 90.0]
    assert profile.horizontal_angles == [0.0]
    assert profile.width == 0.6
    assert profile.length == 0.6
    assert len(profile.candela_table) == 5
    assert profile.candela_table[0][0] == pytest.approx(1008.0)


def test_project_ownership_save_and_copy(test_setup) -> None:
    client = TestClient(app)
    headers_a = {"Authorization": f"Bearer {test_setup['token_a']}"}
    headers_b = {"Authorization": f"Bearer {test_setup['token_b']}"}

    project_payload = {
        "schemaVersion": 1,
        "name": "Headquarters Level 2",
        "sceneName": "Scene 01",
        "room": {
            "polygon": [
                {"x": 0.0, "y": 0.0},
                {"x": 8.0, "y": 0.0},
                {"x": 8.0, "y": 6.0},
                {"x": 0.0, "y": 6.0},
            ],
            "ceilingHeight": 3.0,
            "wallThickness": 0.2,
            "reflectances": {"ceiling": 0.7, "walls": 0.5, "floor": 0.2},
            "obstructions": [],
        },
        "fixtures": [
            {
                "id": "#L-01",
                "name": "Troffer 1",
                "assetId": "asset-troffer-01",
                "position": {"x": 2.0, "y": 2.0, "z": 2.8},
                "rotation": 0.0,
                "tiltAngle": 0.0,
                "aimVector": {"x": 0.0, "y": 0.0, "z": -1.0},
                "luminousFlux": 3600.0,
                "wattage": 40.0,
                "cct": 4000,
                "fluxMultiplier": 1.0,
            }
        ],
        "patterns": [],
        "workplanes": [{"id": "WP-01", "name": "Task", "height": 0.85, "margin": 0.5}],
        "physics": {"maintenanceFactor": 0.8, "radiosity": True},
        "compliance": {
            "standardId": "EN 12464-1 (OFFICE)",
            "targetLux": 500.0,
            "targetUniformity": 0.6,
            "maxOverdesign": 0.3,
        },
        "assets": [],
        "thumbnailObjectKey": "thumbnails/shared/thumb1.png",
    }

    # 1. POST /api/v2/projects creates new project without ID (201 Created)
    res_create = client.post("/api/v2/projects", json=project_payload, headers=headers_a)
    assert res_create.status_code == 201, res_create.text
    created = res_create.json()
    proj_id = created["id"]
    assert proj_id.startswith("proj_")
    assert created["name"] == "Headquarters Level 2"
    assert created["ownerId"] == str(test_setup["user_a"].id)
    assert created["thumbnailUrl"] is not None
    assert created["archiveDownloadUrl"] is not None

    # 2. PUT /api/v2/projects/{id} updates existing project (200 OK)
    project_payload["name"] = "Headquarters Level 2 (Updated)"
    res_update = client.put(f"/api/v2/projects/{proj_id}", json=project_payload, headers=headers_a)
    assert res_update.status_code == 200
    updated = res_update.json()
    assert updated["name"] == "Headquarters Level 2 (Updated)"

    # 3. User B cannot view User A's project (403 Forbidden)
    res_unauth_get = client.get(f"/api/v2/projects/{proj_id}", headers=headers_b)
    assert res_unauth_get.status_code == 403

    # 4. User B cannot update User A's project (403 Forbidden)
    res_unauth_put = client.put(f"/api/v2/projects/{proj_id}", json=project_payload, headers=headers_b)
    assert res_unauth_put.status_code == 403

    # 5. Make a Copy via POST /api/v2/projects/{id}/copy (201 Created)
    res_copy = client.post(f"/api/v2/projects/{proj_id}/copy", headers=headers_a)
    assert res_copy.status_code == 201
    copy_doc = res_copy.json()
    assert copy_doc["id"] != proj_id
    assert copy_doc["name"] == "Copy of Headquarters Level 2 (Updated)"
    assert copy_doc["ownerId"] == str(test_setup["user_a"].id)
    assert copy_doc["archiveDownloadUrl"] is not None

    # 6. Make a Copy with custom name
    res_copy_named = client.post(
        f"/api/v2/projects/{proj_id}/copy",
        json={"name": "Headquarters Variant B"},
        headers=headers_a,
    )
    assert res_copy_named.status_code == 201
    assert res_copy_named.json()["name"] == "Headquarters Variant B"

    # 7. User B cannot copy User A's project (403 Forbidden)
    res_unauth_copy = client.post(f"/api/v2/projects/{proj_id}/copy", headers=headers_b)
    assert res_unauth_copy.status_code == 403

    # 8. List projects returns only caller's projects
    list_a = client.get("/api/v2/projects", headers=headers_a)
    assert list_a.status_code == 200
    items_a = list_a.json()
    assert len(items_a) == 3  # original + 2 copies
    assert all(item["ownerId"] == str(test_setup["user_a"].id) for item in items_a)

    list_b = client.get("/api/v2/projects", headers=headers_b)
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # 9. Export .lxsc
    res_export = client.get(f"/api/v2/projects/{proj_id}/export", headers=headers_a)
    assert res_export.status_code == 200
    assert res_export.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(res_export.content), "r") as zf:
        assert "project.json" in zf.namelist()

    # 10. Delete project
    res_del = client.delete(f"/api/v2/projects/{proj_id}", headers=headers_a)
    assert res_del.status_code == 204

    # 11. Verify 404 after delete
    res_get_del = client.get(f"/api/v2/projects/{proj_id}", headers=headers_a)
    assert res_get_del.status_code == 404
