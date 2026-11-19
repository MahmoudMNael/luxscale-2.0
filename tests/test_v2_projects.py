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
        "name": "Headquarters Level 2",
        "sceneName": "Scene 01",
        "roomCount": 2,
        "thumbnailObjectKey": "thumbnails/shared/thumb1.png",
    }

    # 1. POST /api/v2/projects creates new project without ID (201 Created)
    res_create = client.post("/api/v2/projects", json=project_payload, headers=headers_a)
    assert res_create.status_code == 201, res_create.text
    created = res_create.json()
    proj_id = created["id"]
    assert proj_id.startswith("proj_")
    assert created["name"] == "Headquarters Level 2"
    assert created["roomCount"] == 2
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
    page_a = list_a.json()
    assert page_a["total"] == 3  # original + 2 copies
    assert len(page_a["items"]) == 3
    assert all(item["ownerId"] == str(test_setup["user_a"].id) for item in page_a["items"])

    list_b = client.get("/api/v2/projects", headers=headers_b)
    assert list_b.status_code == 200
    page_b = list_b.json()
    assert page_b["total"] == 0
    assert len(page_b["items"]) == 0

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


def test_project_listing_search_sort_and_pagination(test_setup) -> None:
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {test_setup['token_a']}"}

    def _create_sample(name: str, scene: str, room_count: int):
        payload = {
            "name": name,
            "sceneName": scene,
            "roomCount": room_count,
        }
        res = client.post("/api/v2/projects", json=payload, headers=headers)
        assert res.status_code == 201
        return res.json()

    # Create 3 distinct projects for testing filters, sorting, pagination
    p_alpha = _create_sample(name="Alpha Warehouse", scene="Warehouse Ground", room_count=10)
    p_beta = _create_sample(name="Beta Office", scene="Office Floor 1", room_count=2)
    p_gamma = _create_sample(name="Gamma Clinic", scene="Reception", room_count=5)

    # 1. Search Query on Name
    res_q1 = client.get("/api/v2/projects?query=Warehouse", headers=headers)
    assert res_q1.status_code == 200
    d_q1 = res_q1.json()
    assert d_q1["total"] == 1
    assert d_q1["items"][0]["name"] == "Alpha Warehouse"

    # 2. Search Query on Scene Name
    res_q2 = client.get("/api/v2/projects?query=Reception", headers=headers)
    assert res_q2.status_code == 200
    d_q2 = res_q2.json()
    assert d_q2["total"] == 1
    assert d_q2["items"][0]["name"] == "Gamma Clinic"

    # 3. Non-matching query
    res_q3 = client.get("/api/v2/projects?query=NonExistentTerm", headers=headers)
    assert res_q3.status_code == 200
    assert res_q3.json()["total"] == 0
    assert len(res_q3.json()["items"]) == 0

    # 4. Sorting by name asc
    res_s_asc = client.get("/api/v2/projects?sortBy=name&sortOrder=asc", headers=headers)
    assert res_s_asc.status_code == 200
    names = [item["name"] for item in res_s_asc.json()["items"]]
    assert names == ["Alpha Warehouse", "Beta Office", "Gamma Clinic"]

    # 5. Sorting by name desc
    res_s_desc = client.get("/api/v2/projects?sortBy=name&sortOrder=desc", headers=headers)
    assert res_s_desc.status_code == 200
    names_desc = [item["name"] for item in res_s_desc.json()["items"]]
    assert names_desc == ["Gamma Clinic", "Beta Office", "Alpha Warehouse"]

    # 6. Sorting by roomCount asc
    res_rc_asc = client.get("/api/v2/projects?sortBy=roomCount&sortOrder=asc", headers=headers)
    assert res_rc_asc.status_code == 200
    rc_items = [item["name"] for item in res_rc_asc.json()["items"]]
    assert rc_items == ["Beta Office", "Gamma Clinic", "Alpha Warehouse"]  # 2, 5, 10 rooms

    # 7. Sorting by roomCount desc
    res_rc_desc = client.get("/api/v2/projects?sortBy=roomCount&sortOrder=desc", headers=headers)
    assert res_rc_desc.status_code == 200
    rc_desc_items = [item["name"] for item in res_rc_desc.json()["items"]]
    assert rc_desc_items == ["Alpha Warehouse", "Gamma Clinic", "Beta Office"]

    # 8. Pagination: limit 2, page 1
    res_p1 = client.get("/api/v2/projects?page=1&limit=2&sortBy=name&sortOrder=asc", headers=headers)
    assert res_p1.status_code == 200
    p1_data = res_p1.json()
    assert p1_data["page"] == 1
    assert p1_data["limit"] == 2
    assert p1_data["total"] == 3
    assert p1_data["totalPages"] == 2
    assert len(p1_data["items"]) == 2
    assert p1_data["items"][0]["name"] == "Alpha Warehouse"
    assert p1_data["items"][1]["name"] == "Beta Office"

    # 9. Pagination: limit 2, page 2
    res_p2 = client.get("/api/v2/projects?page=2&limit=2&sortBy=name&sortOrder=asc", headers=headers)
    assert res_p2.status_code == 200
    p2_data = res_p2.json()
    assert p2_data["page"] == 2
    assert p2_data["limit"] == 2
    assert p2_data["total"] == 3
    assert p2_data["totalPages"] == 2
    assert len(p2_data["items"]) == 1
    assert p2_data["items"][0]["name"] == "Gamma Clinic"

