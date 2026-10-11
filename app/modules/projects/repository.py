from __future__ import annotations

from typing import Sequence
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db.session import get_db
from app.modules.projects.entities import ProjectEntity


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

    def list_all(self) -> Sequence[ProjectEntity]:
        stmt = select(ProjectEntity).order_by(ProjectEntity.updated_at.desc())
        return self.db.scalars(stmt).all()

    def delete(self, project_id: str) -> bool:
        entity = self.get_by_id(project_id)
        if not entity:
            return False
        self.db.delete(entity)
        self.db.commit()
        return True


def get_project_repository(db: Session = Depends(get_db)) -> ProjectRepository:
    return ProjectRepository(db)
