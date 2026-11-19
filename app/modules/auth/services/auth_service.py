from __future__ import annotations

import base64
import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse
from typing import Any
from fastapi import Depends
import httpx
import jwt
from jwt import PyJWKClient

from app.modules.auth.entities.account_entity import AccountEntity
from app.modules.auth.repositories.account_repository import AccountRepository, get_account_repository
from app.modules.users.entities.user_entity import UserEntity
from app.modules.users.repositories.user_repository import UserRepository, get_user_repository

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(
        self,
        user_repo: UserRepository,
        account_repo: AccountRepository,
    ) -> None:
        self.user_repo = user_repo
        self.account_repo = account_repo

        self.idp_issuer_url = os.getenv("IDP_ISSUER_URL", "http://localhost:8000").rstrip("/")
        self.idp_client_id = os.getenv("IDP_CLIENT_ID", "lxscale")
        self.idp_client_secret = os.getenv("IDP_CLIENT_SECRET", "lxscale-secret")
        self.idp_redirect_uri = os.getenv("IDP_REDIRECT_URI", "http://localhost:8001/api/v2/auth/callback")
        self.auth_secret_key = os.getenv("AUTH_SECRET_KEY", "lxscale-development-secret-key-change-in-prod")
        self.access_token_ttl = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15")) * 60
        self.refresh_token_days = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
        self.cookie_domain = os.getenv("COOKIE_DOMAIN") or None
        self.cookie_secure = os.getenv("COOKIE_SECURE", "false").lower() in ("true", "1")

        self.allowed_origins = [
            o.strip().rstrip("/")
            for o in os.getenv("ALLOWED_FRONTEND_ORIGINS", "http://localhost:4200,http://localhost:4201,https://app.lxscale.com,https://lxscale.com").split(",")
            if o.strip()
        ]

        self._jwks_client: PyJWKClient | None = None

    @property
    def jwks_client(self) -> PyJWKClient:
        if self._jwks_client is None:
            jwks_url = f"{self.idp_issuer_url}/.well-known/jwks.json"
            self._jwks_client = PyJWKClient(jwks_url)
        return self._jwks_client

    def validate_return_to(self, return_to: str | None) -> str:
        if not return_to:
            return "/"
        try:
            parsed = urlparse(return_to)
            if not parsed.netloc:
                return return_to if return_to.startswith("/") else "/"
            origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
            for allowed in self.allowed_origins:
                if allowed == origin or allowed.endswith(f".{parsed.netloc}") or parsed.netloc.endswith(".lxscale.com"):
                    return return_to
            return "/"
        except Exception:
            return "/"

    def generate_pkce(self) -> tuple[str, str]:
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return verifier, challenge

    def create_flow_state_token(self, state: str, nonce: str, verifier: str, return_to: str) -> str:
        payload = {
            "state": state,
            "nonce": nonce,
            "verifier": verifier,
            "return_to": return_to,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
        }
        return jwt.encode(payload, self.auth_secret_key, algorithm="HS256")

    def decode_flow_state_token(self, token: str) -> dict[str, Any] | None:
        try:
            return jwt.decode(token, self.auth_secret_key, algorithms=["HS256"])
        except Exception:
            return None

    def build_authorize_url(self, return_to: str | None = None) -> tuple[str, str]:
        safe_return_to = self.validate_return_to(return_to)
        verifier, challenge = self.generate_pkce()
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)

        params = {
            "client_id": self.idp_client_id,
            "redirect_uri": self.idp_redirect_uri,
            "response_type": "code",
            "scope": "openid email profile idp_roles offline_access",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "nonce": nonce,
        }
        authorize_url = f"{self.idp_issuer_url}/authorize?{urlencode(params)}"
        flow_cookie = self.create_flow_state_token(state, nonce, verifier, safe_return_to)
        return authorize_url, flow_cookie

    async def exchange_code_and_authenticate(
        self,
        code: str,
        state: str,
        flow_state_token: str | None,
    ) -> tuple[bool, UserEntity | None, str | None, str | None, str]:
        if not flow_state_token:
            return False, None, None, "missing_state", "/"

        flow_data = self.decode_flow_state_token(flow_state_token)
        if not flow_data or flow_data.get("state") != state:
            return False, None, None, "invalid_state", "/"

        return_to = flow_data.get("return_to") or "/"
        verifier = flow_data.get("verifier")
        expected_nonce = flow_data.get("nonce")

        token_url = f"{self.idp_issuer_url}/token"
        token_payload = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.idp_redirect_uri,
            "code_verifier": verifier,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    token_url,
                    data=token_payload,
                    auth=(self.idp_client_id, self.idp_client_secret),
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if resp.status_code != 200:
                    logger.error(f"sc-idp token exchange failed: {resp.status_code} {resp.text}")
                    return False, None, None, "idp_token_error", return_to
                token_response = resp.json()
        except Exception as exc:
            logger.error(f"Error connecting to sc-idp: {exc}")
            return False, None, None, "idp_connection_error", return_to

        idp_refresh_token = token_response.get("refresh_token")
        id_token_raw = token_response.get("id_token")
        if not id_token_raw:
            return False, None, None, "missing_id_token", return_to

        try:
            signing_key = self.jwks_client.get_signing_key_from_jwt(id_token_raw)
            claims = jwt.decode(
                id_token_raw,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.idp_client_id,
                issuer=self.idp_issuer_url,
            )
        except Exception as exc:
            logger.error(f"JWT validation failed: {exc}")
            return False, None, None, "invalid_id_token", return_to

        if claims.get("nonce") != expected_nonce:
            return False, None, None, "nonce_mismatch", return_to

        sub = str(claims["sub"])
        email = claims.get("email") or f"{sub}@sc-idp.local"
        name = claims.get("name") or claims.get("given_name") or email.split("@")[0]
        idp_roles = claims.get("idp_roles") or claims.get("roles") or []
        role = "admin" if "admin" in idp_roles else "user"

        user = self.upsert_user(sub, email, name, role, id_token_raw, idp_refresh_token)
        product_refresh_token = self.mint_product_refresh_token(user.id)
        return True, user, product_refresh_token, None, return_to

    def upsert_user(
        self,
        sub: str,
        email: str,
        name: str,
        role: str,
        id_token: str | None,
        refresh_token: str | None = None,
    ) -> UserEntity:
        account = self.account_repo.get_by_provider_account("sc_idp", sub)
        if account:
            user = self.user_repo.get_by_id(account.user_id)
            if user:
                user.email = email
                user.name = name
                user.role = role
                self.user_repo.save(user)
                account.id_token = id_token
                if refresh_token:
                    account.refresh_token = refresh_token
                self.account_repo.save(account)
                return user

        # Check existing user by email
        user = self.user_repo.get_by_email(email)
        if not user:
            user = UserEntity(email=email, name=name, role=role)
            user = self.user_repo.save(user)

        new_account = AccountEntity(
            user_id=user.id,
            provider="sc_idp",
            provider_account_id=sub,
            id_token=id_token,
            refresh_token=refresh_token,
        )
        self.account_repo.save(new_account)
        return user

    def mint_product_access_token(self, user: UserEntity) -> tuple[str, int]:
        exp = datetime.now(timezone.utc) + timedelta(seconds=self.access_token_ttl)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "type": "access",
            "exp": exp,
        }
        token = jwt.encode(payload, self.auth_secret_key, algorithm="HS256")
        return token, self.access_token_ttl

    def mint_product_refresh_token(self, user_id: uuid.UUID) -> str:
        exp = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_days)
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "jti": secrets.token_hex(16),
            "exp": exp,
        }
        return jwt.encode(payload, self.auth_secret_key, algorithm="HS256")

    def verify_access_token(self, token: str) -> dict[str, Any] | None:
        try:
            payload = jwt.decode(token, self.auth_secret_key, algorithms=["HS256"])
            if payload.get("type") != "access":
                return None
            return payload
        except Exception:
            return None

    async def refresh_tokens(self, refresh_token: str) -> tuple[str, int, str, UserEntity] | None:
        try:
            payload = jwt.decode(refresh_token, self.auth_secret_key, algorithms=["HS256"])
        except Exception:
            return None

        if payload.get("type") != "refresh":
            return None

        user_id_str = payload.get("sub")
        if not user_id_str:
            return None

        try:
            user_id = uuid.UUID(user_id_str)
        except ValueError:
            return None

        user = self.user_repo.get_by_id(user_id)
        if not user:
            return None

        # Synchronize with sc-idp if an offline refresh token exists
        accounts = self.account_repo.get_by_user_id(user.id)
        idp_account = next((a for a in accounts if a.provider == "sc_idp" and a.refresh_token), None)

        if idp_account and idp_account.refresh_token:
            token_url = f"{self.idp_issuer_url}/token"
            refresh_payload = {
                "grant_type": "refresh_token",
                "refresh_token": idp_account.refresh_token,
                "scope": "openid email profile idp_roles offline_access",
            }
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        token_url,
                        data=refresh_payload,
                        auth=(self.idp_client_id, self.idp_client_secret),
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )
                    if resp.status_code == 400:
                        # Revoked by user in sc-idp
                        idp_account.refresh_token = None
                        self.account_repo.save(idp_account)
                        return None
                    elif resp.status_code == 200:
                        data = resp.json()
                        new_idp_refresh = data.get("refresh_token")
                        if new_idp_refresh:
                            idp_account.refresh_token = new_idp_refresh
                            self.account_repo.save(idp_account)
            except Exception as exc:
                logger.warning(f"Failed to sync refresh token with sc-idp: {exc}")

        # Rotate product refresh token and mint access token
        access_token, expires_in = self.mint_product_access_token(user)
        new_product_refresh = self.mint_product_refresh_token(user.id)
        return access_token, expires_in, new_product_refresh, user


def get_auth_service(
    user_repo: UserRepository = Depends(get_user_repository),
    account_repo: AccountRepository = Depends(get_account_repository),
) -> AuthService:
    return AuthService(user_repo, account_repo)
