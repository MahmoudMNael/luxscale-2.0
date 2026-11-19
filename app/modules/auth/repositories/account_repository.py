from __future__ import annotations

import uuid
from typing import Any, Sequence
from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.db.session import get_db
from app.modules.auth.entities.account_entity import AccountEntity


class AccountRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_provider_account(self, provider: str, provider_account_id: str) -> AccountEntity | None:
        stmt = select(AccountEntity).where(
            AccountEntity.provider == provider,
            AccountEntity.provider_account_id == provider_account_id,
        )
        return self.db.scalars(stmt).first()

    def get_by_user_id(self, user_id: uuid.UUID) -> Sequence[AccountEntity]:
        stmt = select(AccountEntity).where(AccountEntity.user_id == user_id)
        return self.db.scalars(stmt).all()

    def save(self, account: AccountEntity) -> AccountEntity:
        merged = self.db.merge(account)
        self.db.commit()
        self.db.refresh(merged)
        return merged

    def update(self, account_id: uuid.UUID, values: dict[str, Any]) -> AccountEntity | None:
        stmt = (
            update(AccountEntity)
            .where(AccountEntity.id == account_id)
            .values(**values)
        )
        self.db.execute(stmt)
        self.db.commit()
        stmt_get = select(AccountEntity).where(AccountEntity.id == account_id)
        return self.db.scalars(stmt_get).first()


def get_account_repository(db: Session = Depends(get_db)) -> AccountRepository:
    return AccountRepository(db)
