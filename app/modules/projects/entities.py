from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from sqlalchemy import DateTime, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base


class ProjectEntity(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    scene_name: Mapped[str] = mapped_column(String(256), nullable=False, default="Scene 01")
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
