from __future__ import annotations

import uuid
from typing import Sequence
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db.session import get_db
from app.modules.projects.entities.project_entity import ProjectEntity


class ProjectRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def save(self, entity: ProjectEntity) -> ProjectEntity:
        merged = self.db.merge(entity)
        self.db.commit()
        self.db.refresh(merged)
        return merged

    def get_by_id(self, project_id: str) -> ProjectEntity | None:
        stmt = select(ProjectEntity).where(ProjectEntity.id == project_id)
        return self.db.scalars(stmt).first()

    def get_by_id_and_user(self, project_id: str, user_id: uuid.UUID) -> ProjectEntity | None:
        stmt = select(ProjectEntity).where(
            ProjectEntity.id == project_id,
            ProjectEntity.user_id == user_id,
        )
        return self.db.scalars(stmt).first()

    def list_by_user(self, user_id: uuid.UUID) -> Sequence[ProjectEntity]:
        stmt = (
            select(ProjectEntity)
            .where(ProjectEntity.user_id == user_id)
            .order_by(ProjectEntity.updated_at.desc())
        )
        return self.db.scalars(stmt).all()

    def delete(self, project_id: str, user_id: uuid.UUID) -> bool:
        entity = self.get_by_id_and_user(project_id, user_id)
        if not entity:
            return False
        self.db.delete(entity)
        self.db.commit()
        return True


def get_project_repository(db: Session = Depends(get_db)) -> ProjectRepository:
    return ProjectRepository(db)
