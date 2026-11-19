from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.modules.auth.dependencies import get_current_user
from app.modules.users.dtos.requests import UpdateSignatureRequestDto, UpdatePreferencesRequestDto
from app.modules.users.dtos.responses import SignatureResponseDto, PreferencesResponseDto
from app.modules.users.entities.user_entity import UserEntity
from app.modules.users.services.user_service import UserService, get_user_service

router = APIRouter(prefix="/api/v2/users", tags=["V2 Users"])


@router.get(
    "/me/signature",
    response_model=SignatureResponseDto,
    summary="Get current user signature",
    description="Returns the user signature used on reports, including resolved logo download URL.",
)
def get_signature(
    current_user: UserEntity = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> SignatureResponseDto:
    return service.get_or_create_signature(current_user.id)


@router.put(
    "/me/signature",
    response_model=SignatureResponseDto,
    summary="Update current user signature",
    description="Updates user signature fields (name, email, phone, company, title, logoObjectKey, dynamic extraFields).",
)
def update_signature(
    body: UpdateSignatureRequestDto,
    current_user: UserEntity = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> SignatureResponseDto:
    return service.update_signature(current_user.id, body)


@router.get(
    "/me/preferences",
    response_model=PreferencesResponseDto,
    summary="Get current user preferences",
    description="Returns user preferences (UI theme, metric/imperial units, calculations presets).",
)
def get_preferences(
    current_user: UserEntity = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> PreferencesResponseDto:
    return service.get_or_create_preferences(current_user.id)


@router.put(
    "/me/preferences",
    response_model=PreferencesResponseDto,
    summary="Update current user preferences",
    description="Updates user preferences dictionary.",
)
def update_preferences(
    body: UpdatePreferencesRequestDto,
    current_user: UserEntity = Depends(get_current_user),
    service: UserService = Depends(get_user_service),
) -> PreferencesResponseDto:
    return service.update_preferences(current_user.id, body)
