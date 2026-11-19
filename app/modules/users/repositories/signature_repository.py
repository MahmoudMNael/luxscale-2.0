from __future__ import annotations

import uuid
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db.session import get_db
from app.modules.users.entities.signature_entity import UserSignatureEntity


class UserSignatureRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_user_id(self, user_id: uuid.UUID) -> UserSignatureEntity | None:
        stmt = select(UserSignatureEntity).where(UserSignatureEntity.user_id == user_id)
        return self.db.scalars(stmt).first()

    def save(self, signature: UserSignatureEntity) -> UserSignatureEntity:
        merged = self.db.merge(signature)
        self.db.commit()
        self.db.refresh(merged)
        return merged


def get_signature_repository(db: Session = Depends(get_db)) -> UserSignatureRepository:
    return UserSignatureRepository(db)
