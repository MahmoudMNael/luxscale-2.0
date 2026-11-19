from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db.base import Base


class UserEntity(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="user")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    accounts = relationship("AccountEntity", back_populates="user", cascade="all, delete-orphan")
    signature = relationship("UserSignatureEntity", back_populates="user", uselist=False, cascade="all, delete-orphan")
    preferences = relationship("UserPreferenceEntity", back_populates="user", uselist=False, cascade="all, delete-orphan")
