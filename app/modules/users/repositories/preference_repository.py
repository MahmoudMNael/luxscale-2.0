from __future__ import annotations

import uuid
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db.session import get_db
from app.modules.users.entities.preference_entity import UserPreferenceEntity


class UserPreferenceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_user_id(self, user_id: uuid.UUID) -> UserPreferenceEntity | None:
        stmt = select(UserPreferenceEntity).where(UserPreferenceEntity.user_id == user_id)
        return self.db.scalars(stmt).first()

    def save(self, preference: UserPreferenceEntity) -> UserPreferenceEntity:
        merged = self.db.merge(preference)
        self.db.commit()
        self.db.refresh(merged)
        return merged


def get_preference_repository(db: Session = Depends(get_db)) -> UserPreferenceRepository:
    return UserPreferenceRepository(db)
