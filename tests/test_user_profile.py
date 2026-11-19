from __future__ import annotations

import uuid
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
from app.modules.users.entities.user_entity import UserEntity
from app.modules.users.repositories.user_repository import UserRepository


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_user_signature_and_preferences(db_session, tmp_path: Path):
    user_repo = UserRepository(db_session)
    account_repo = AccountRepository(db_session)
    auth_service = AuthService(user_repo, account_repo)
    storage_provider = LocalStorageProvider(base_dir=tmp_path, base_url="http://storage.local", secret="sec")
    storage_service = StorageService(provider=storage_provider)

    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_auth_service] = lambda: auth_service
    app.dependency_overrides[get_storage_service] = lambda: storage_service

    client = TestClient(app)

    try:
        user = UserEntity(email="architect@lxscale.com", name="Architect One", role="user")
        user = user_repo.save(user)
        access_token, _ = auth_service.mint_product_access_token(user)
        auth_headers = {"Authorization": f"Bearer {access_token}"}

        # 1. Signature defaults
        get_sig = client.get("/api/v2/users/me/signature", headers=auth_headers)
        assert get_sig.status_code == 200
        sig_data = get_sig.json()
        assert sig_data["userId"] == str(user.id)
        assert sig_data["logoUrl"] is None

        # 2. Update signature with logoObjectKey & custom fields
        put_sig = client.put(
            "/api/v2/users/me/signature",
            headers=auth_headers,
            json={
                "name": "Architect One, PE",
                "email": "architect@lxscale.com",
                "phone": "+1-555-0199",
                "company": "Studio Illuminance",
                "title": "Principal Lighting Designer",
                "logoObjectKey": "signatures/architect/logo.png",
                "extraFields": {
                    "licenseNumber": "PE-998822",
                    "registrationState": "CA",
                    "website": "https://illuminance.studio",
                },
            },
        )
        assert put_sig.status_code == 200
        updated_sig = put_sig.json()
        assert updated_sig["name"] == "Architect One, PE"
        assert updated_sig["company"] == "Studio Illuminance"
        assert updated_sig["extraFields"]["licenseNumber"] == "PE-998822"
        # Logo URL was dynamically resolved via storage service
        assert updated_sig["logoUrl"] is not None
        assert "http://storage.local/api/v2/storage/raw/" in updated_sig["logoUrl"]

        # 3. Preferences defaults
        get_pref = client.get("/api/v2/users/me/preferences", headers=auth_headers)
        assert get_pref.status_code == 200
        pref_data = get_pref.json()
        assert pref_data["userId"] == str(user.id)
        assert pref_data["preferences"] == {}

        # 4. Update preferences
        put_pref = client.put(
            "/api/v2/users/me/preferences",
            headers=auth_headers,
            json={
                "preferences": {
                    "theme": "dark",
                    "units": "metric",
                    "defaultCeilingHeight": 3.2,
                    "autoCalculate": True,
                }
            },
        )
        assert put_pref.status_code == 200
        updated_pref = put_pref.json()
        assert updated_pref["preferences"]["theme"] == "dark"
        assert updated_pref["preferences"]["defaultCeilingHeight"] == 3.2

        # 5. Missing auth returns 401
        unauth_sig = client.get("/api/v2/users/me/signature")
        assert unauth_sig.status_code == 401

        unauth_pref = client.get("/api/v2/users/me/preferences")
        assert unauth_pref.status_code == 401
    finally:
        app.dependency_overrides.clear()
