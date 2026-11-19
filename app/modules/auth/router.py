from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.dtos.requests import RefreshTokenRequestDto
from app.modules.auth.dtos.responses import (
    LogoutResponseDto,
    TokenResponseDto,
    UserMeResponseDto,
    UserSummaryResponseDto,
)
from app.modules.auth.services.auth_service import AuthService, get_auth_service
from app.modules.users.entities.user_entity import UserEntity
from app.modules.users.services.user_service import UserService, get_user_service

router = APIRouter(prefix="/api/v2/auth", tags=["V2 Auth"])

FLOW_COOKIE_NAME = "lxscale_auth_flow"
REFRESH_COOKIE_NAME = "lxscale_refresh_token"


@router.get(
    "/login",
    summary="Initiate sc-idp SSO login flow",
    description="Generates PKCE pair, sets flow state cookie, and redirects user to sc-idp login.",
)
def login(
    return_to: str | None = None,
    service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    authorize_url, flow_cookie = service.build_authorize_url(return_to)
    response = RedirectResponse(url=authorize_url, status_code=status.HTTP_302_FOUND)
    response.set_cookie(
        key=FLOW_COOKIE_NAME,
        value=flow_cookie,
        max_age=600,
        httponly=True,
        samesite="lax",
        secure=service.cookie_secure,
        domain=service.cookie_domain,
        path="/",
    )
    return response


@router.get(
    "/callback",
    summary="Handle sc-idp OAuth authorization callback",
    description="Exchanges code for tokens, verifies sc-idp identity, stores offline refresh token, sets shared SSO refresh cookie, and redirects to frontend.",
)
async def callback(
    code: str,
    state: str,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> RedirectResponse:
    flow_cookie = request.cookies.get(FLOW_COOKIE_NAME)
    success, user, refresh_token, error_code, return_to = await service.exchange_code_and_authenticate(
        code=code,
        state=state,
        flow_state_token=flow_cookie,
    )

    if not success or not refresh_token:
        sep = "&" if "?" in return_to else "?"
        error_url = f"{return_to}{sep}error={error_code or 'auth_failed'}"
        res = RedirectResponse(url=error_url, status_code=status.HTTP_302_FOUND)
        res.delete_cookie(key=FLOW_COOKIE_NAME, domain=service.cookie_domain, path="/")
        return res

    response = RedirectResponse(url=return_to, status_code=status.HTTP_302_FOUND)
    # Set shared SSO refresh token cookie (shared across app.lxscale.com, lxscale.com)
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        max_age=service.refresh_token_days * 86400,
        httponly=True,
        samesite="lax",
        secure=service.cookie_secure,
        domain=service.cookie_domain,
        path="/",
    )
    response.delete_cookie(key=FLOW_COOKIE_NAME, domain=service.cookie_domain, path="/")
    return response


@router.post(
    "/refresh",
    response_model=TokenResponseDto,
    summary="Refresh access token using SSO refresh cookie",
    description="Exchanges the HTTP-only refresh cookie for a fresh access token, rotating the refresh token.",
)
async def refresh_token_endpoint(
    response: Response,
    body: RefreshTokenRequestDto | None = None,
    cookie_token: str | None = Cookie(None, alias=REFRESH_COOKIE_NAME),
    service: AuthService = Depends(get_auth_service),
) -> TokenResponseDto:
    raw_token = (body.refreshToken if body else None) or cookie_token
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing refresh token",
        )

    result = await service.refresh_tokens(raw_token)
    if not result:
        response.delete_cookie(key=REFRESH_COOKIE_NAME, domain=service.cookie_domain, path="/")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    access_token, expires_in, new_product_refresh, user = result

    # Rotate shared SSO refresh cookie
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=new_product_refresh,
        max_age=service.refresh_token_days * 86400,
        httponly=True,
        samesite="lax",
        secure=service.cookie_secure,
        domain=service.cookie_domain,
        path="/",
    )

    return TokenResponseDto(
        accessToken=access_token,
        tokenType="Bearer",
        expiresIn=expires_in,
        user=UserSummaryResponseDto(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role=user.role,
        ),
    )


@router.post(
    "/logout",
    response_model=LogoutResponseDto,
    summary="Log out and clear shared SSO session",
    description="Clears the shared SSO session cookie and returns sc-idp end-session logout URL.",
)
def logout(
    response: Response,
    service: AuthService = Depends(get_auth_service),
) -> LogoutResponseDto:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, domain=service.cookie_domain, path="/")
    logout_url = f"{service.idp_issuer_url}/logout"
    return LogoutResponseDto(logoutUrl=logout_url)


@router.get(
    "/me",
    response_model=UserMeResponseDto,
    summary="Get current user identity, signature, and preferences",
)
def get_me(
    current_user: UserEntity = Depends(get_current_user),
    user_service: UserService = Depends(get_user_service),
) -> UserMeResponseDto:
    sig = user_service.get_or_create_signature(current_user.id)
    prefs = user_service.get_or_create_preferences(current_user.id)
    return UserMeResponseDto(
        id=str(current_user.id),
        email=current_user.email,
        name=current_user.name,
        role=current_user.role,
        signature=sig,
        preferences=prefs.preferences,
    )
