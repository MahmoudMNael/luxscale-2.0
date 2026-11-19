from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from fastapi.testclient import TestClient
import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.core.db.base import Base
from app.core.db.session import get_db
from app.modules.auth.entities.account_entity import AccountEntity
from app.modules.auth.repositories.account_repository import AccountRepository
from app.modules.auth.services.auth_service import AuthService, get_auth_service
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


@pytest.fixture
def auth_service(db_session):
    user_repo = UserRepository(db_session)
    account_repo = AccountRepository(db_session)
    service = AuthService(user_repo, account_repo)
    service.auth_secret_key = "test-secret-key-12345678901234567890"
    service.cookie_domain = ".lxscale.com"
    return service


def test_build_authorize_url(auth_service: AuthService):
    # Allowed origin
    auth_url, flow_token = auth_service.build_authorize_url("https://app.lxscale.com/dashboard")
    assert "https://app.lxscale.com/dashboard" in auth_url or "response_type=code" in auth_url
    assert "scope=openid+email+profile+idp_roles+offline_access" in auth_url
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url

    decoded = auth_service.decode_flow_state_token(flow_token)
    assert decoded is not None
    assert decoded["return_to"] == "https://app.lxscale.com/dashboard"
    assert "verifier" in decoded
    assert "nonce" in decoded

    # Untrusted domain fallback to /
    _, untrusted_flow = auth_service.build_authorize_url("https://malicious-site.com/steal")
    decoded_untrusted = auth_service.decode_flow_state_token(untrusted_flow)
    assert decoded_untrusted["return_to"] == "/"


@pytest.mark.anyio
async def test_exchange_code_and_authenticate(auth_service: AuthService, db_session):
    # Generate RSA key for ID token simulation
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()

    _, flow_token = auth_service.build_authorize_url("https://app.lxscale.com/welcome")
    flow_data = auth_service.decode_flow_state_token(flow_token)
    state = flow_data["state"]
    nonce = flow_data["nonce"]

    id_token_claims = {
        "iss": auth_service.idp_issuer_url,
        "sub": "user-sc-idp-uuid-999",
        "aud": auth_service.idp_client_id,
        "nonce": nonce,
        "email": "designer@lxscale.com",
        "name": "Jane Lighting",
        "idp_roles": ["designer"],
        "exp": int(datetime.now(timezone.utc).timestamp()) + 3600,
    }
    mock_id_token = jwt.encode(id_token_claims, private_pem, algorithm="RS256", headers={"kid": "test-kid"})

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "idp-mock-access-token",
        "refresh_token": "idp-mock-offline-refresh-token",
        "id_token": mock_id_token,
        "token_type": "Bearer",
        "expires_in": 3600,
    }

    mock_jwk_key = MagicMock()
    mock_jwk_key.key = public_key

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp), \
         patch.object(auth_service.jwks_client, "get_signing_key_from_jwt", return_value=mock_jwk_key):

        success, user, product_refresh, err, return_to = await auth_service.exchange_code_and_authenticate(
            code="test-auth-code",
            state=state,
            flow_state_token=flow_token,
        )

        assert success is True
        assert err is None
        assert return_to == "https://app.lxscale.com/welcome"
        assert user is not None
        assert user.email == "designer@lxscale.com"
        assert user.name == "Jane Lighting"
        assert product_refresh is not None

        # Verify DB records
        user_repo = UserRepository(db_session)
        account_repo = AccountRepository(db_session)
        db_user = user_repo.get_by_email("designer@lxscale.com")
        assert db_user is not None
        account = account_repo.get_by_provider_account("sc_idp", "user-sc-idp-uuid-999")
        assert account is not None
        assert account.refresh_token == "idp-mock-offline-refresh-token"


@pytest.mark.anyio
async def test_refresh_tokens(auth_service: AuthService, db_session):
    user_repo = UserRepository(db_session)
    account_repo = AccountRepository(db_session)

    user = UserEntity(email="john@lxscale.com", name="John", role="user")
    user = user_repo.save(user)

    account = AccountEntity(
        user_id=user.id,
        provider="sc_idp",
        provider_account_id="sc-sub-111",
        refresh_token="idp-refresh-token-111",
    )
    account_repo.save(account)

    product_refresh = auth_service.mint_product_refresh_token(user.id)

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "new-idp-access",
        "refresh_token": "rotated-idp-refresh",
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
        res = await auth_service.refresh_tokens(product_refresh)
        assert res is not None
        access_token, expires_in, new_product_refresh, refreshed_user = res
        assert access_token is not None
        assert expires_in == auth_service.access_token_ttl
        assert new_product_refresh != product_refresh
        assert refreshed_user.id == user.id

        # Check that rotated idp refresh token was updated in account
        updated_account = account_repo.get_by_provider_account("sc_idp", "sc-sub-111")
        assert updated_account.refresh_token == "rotated-idp-refresh"


def test_auth_api_routes(db_session, auth_service: AuthService):
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_auth_service] = lambda: auth_service

    client = TestClient(app)

    try:
        # 1. Login redirect
        login_resp = client.get("/api/v2/auth/login?return_to=https://app.lxscale.com/studio", follow_redirects=False)
        assert login_resp.status_code == 302
        assert "lxscale_auth_flow" in login_resp.headers.get("set-cookie", "")

        # 2. Refresh without cookie returns 401
        ref_fail = client.post("/api/v2/auth/refresh")
        assert ref_fail.status_code == 401

        # 3. Create user and mint refresh token
        user_repo = UserRepository(db_session)
        test_user = UserEntity(email="test@lxscale.com", name="Test User", role="user")
        test_user = user_repo.save(test_user)

        refresh_token = auth_service.mint_product_refresh_token(test_user.id)
        access_token, _ = auth_service.mint_product_access_token(test_user)

        # 4. Refresh with valid token body
        ref_ok = client.post("/api/v2/auth/refresh", json={"refreshToken": refresh_token})
        assert ref_ok.status_code == 200
        ref_data = ref_ok.json()
        assert "accessToken" in ref_data
        assert ref_data["user"]["email"] == "test@lxscale.com"
        # Shared cookie domain in header
        cookie_header = ref_ok.headers.get("set-cookie", "")
        assert "domain=.lxscale.com" in cookie_header.lower()

        # 5. GET /api/v2/auth/me with Bearer token
        me_resp = client.get("/api/v2/auth/me", headers={"Authorization": f"Bearer {access_token}"})
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["email"] == "test@lxscale.com"
        assert me_data["signature"] is not None
        assert me_data["preferences"] is not None

        # 6. Logout clears cookie
        logout_resp = client.post("/api/v2/auth/logout")
        assert logout_resp.status_code == 200
        assert "logoutUrl" in logout_resp.json()
    finally:
        app.dependency_overrides.clear()
