from __future__ import annotations

import uuid
from typing import Any
from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.db.session import get_db
from app.modules.users.entities.user_entity import UserEntity


class UserRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, user_id: uuid.UUID) -> UserEntity | None:
        stmt = select(UserEntity).where(UserEntity.id == user_id)
        return self.db.scalars(stmt).first()

    def get_by_email(self, email: str) -> UserEntity | None:
        stmt = select(UserEntity).where(UserEntity.email == email.lower().strip())
        return self.db.scalars(stmt).first()

    def save(self, user: UserEntity) -> UserEntity:
        merged = self.db.merge(user)
        self.db.commit()
        self.db.refresh(merged)
        return merged

    def update(self, user_id: uuid.UUID, values: dict[str, Any]) -> UserEntity | None:
        stmt = (
            update(UserEntity)
            .where(UserEntity.id == user_id)
            .values(**values)
        )
        self.db.execute(stmt)
        self.db.commit()
        return self.get_by_id(user_id)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)
