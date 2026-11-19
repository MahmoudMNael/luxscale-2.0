from __future__ import annotations

import uuid
from fastapi import Depends

from app.core.storage.services.storage_service import StorageService, get_storage_service
from app.modules.users.dtos.requests import UpdateSignatureRequestDto, UpdatePreferencesRequestDto
from app.modules.users.dtos.responses import SignatureResponseDto, PreferencesResponseDto
from app.modules.users.entities.signature_entity import UserSignatureEntity
from app.modules.users.entities.preference_entity import UserPreferenceEntity
from app.modules.users.repositories.signature_repository import UserSignatureRepository, get_signature_repository
from app.modules.users.repositories.preference_repository import UserPreferenceRepository, get_preference_repository


class UserService:
    def __init__(
        self,
        signature_repo: UserSignatureRepository,
        preference_repo: UserPreferenceRepository,
        storage_service: StorageService,
    ) -> None:
        self.signature_repo = signature_repo
        self.preference_repo = preference_repo
        self.storage_service = storage_service

    def _to_signature_dto(self, entity: UserSignatureEntity) -> SignatureResponseDto:
        logo_url = None
        if entity.logo_object_key:
            logo_url = self.storage_service.generate_download_url(entity.logo_object_key)

        return SignatureResponseDto(
            id=str(entity.id),
            userId=str(entity.user_id),
            name=entity.name,
            email=entity.email,
            phone=entity.phone,
            company=entity.company,
            title=entity.title,
            logoObjectKey=entity.logo_object_key,
            logoUrl=logo_url,
            extraFields=entity.extra_fields or {},
            updatedAt=entity.updated_at.isoformat(),
        )

    def _to_preferences_dto(self, entity: UserPreferenceEntity) -> PreferencesResponseDto:
        return PreferencesResponseDto(
            id=str(entity.id),
            userId=str(entity.user_id),
            preferences=entity.preferences_json or {},
            updatedAt=entity.updated_at.isoformat(),
        )

    def get_or_create_signature(self, user_id: uuid.UUID) -> SignatureResponseDto:
        entity = self.signature_repo.get_by_user_id(user_id)
        if not entity:
            entity = UserSignatureEntity(user_id=user_id, extra_fields={})
            entity = self.signature_repo.save(entity)
        return self._to_signature_dto(entity)

    def update_signature(self, user_id: uuid.UUID, dto: UpdateSignatureRequestDto) -> SignatureResponseDto:
        entity = self.signature_repo.get_by_user_id(user_id)
        if not entity:
            entity = UserSignatureEntity(user_id=user_id, extra_fields={})

        if dto.name is not None:
            entity.name = dto.name
        if dto.email is not None:
            entity.email = dto.email
        if dto.phone is not None:
            entity.phone = dto.phone
        if dto.company is not None:
            entity.company = dto.company
        if dto.title is not None:
            entity.title = dto.title
        if dto.logoObjectKey is not None:
            entity.logo_object_key = dto.logoObjectKey
        if dto.extraFields is not None:
            entity.extra_fields = dto.extraFields

        saved = self.signature_repo.save(entity)
        return self._to_signature_dto(saved)

    def get_or_create_preferences(self, user_id: uuid.UUID) -> PreferencesResponseDto:
        entity = self.preference_repo.get_by_user_id(user_id)
        if not entity:
            entity = UserPreferenceEntity(user_id=user_id, preferences_json={})
            entity = self.preference_repo.save(entity)
        return self._to_preferences_dto(entity)

    def update_preferences(self, user_id: uuid.UUID, dto: UpdatePreferencesRequestDto) -> PreferencesResponseDto:
        entity = self.preference_repo.get_by_user_id(user_id)
        if not entity:
            entity = UserPreferenceEntity(user_id=user_id, preferences_json={})

        entity.preferences_json = dto.preferences
        saved = self.preference_repo.save(entity)
        return self._to_preferences_dto(saved)


def get_user_service(
    signature_repo: UserSignatureRepository = Depends(get_signature_repository),
    preference_repo: UserPreferenceRepository = Depends(get_preference_repository),
    storage_service: StorageService = Depends(get_storage_service),
) -> UserService:
    return UserService(signature_repo, preference_repo, storage_service)
