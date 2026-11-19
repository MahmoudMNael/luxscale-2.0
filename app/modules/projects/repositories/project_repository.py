from __future__ import annotations

import uuid
from typing import Sequence
from fastapi import Depends
from sqlalchemy import func, or_, select
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

    def count_by_user(
        self,
        user_id: uuid.UUID,
        query: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(ProjectEntity).where(ProjectEntity.user_id == user_id)
        if query and query.strip():
            term = f"%{query.strip()}%"
            stmt = stmt.where(or_(ProjectEntity.name.ilike(term), ProjectEntity.scene_name.ilike(term)))
        return self.db.scalar(stmt) or 0

    def list_by_user(
        self,
        user_id: uuid.UUID,
        query: str | None = None,
        sort_by: str = "updatedAt",
        sort_order: str = "desc",
        limit: int = 20,
        offset: int = 0,
    ) -> Sequence[ProjectEntity]:
        stmt = select(ProjectEntity).where(ProjectEntity.user_id == user_id)

        if query and query.strip():
            term = f"%{query.strip()}%"
            stmt = stmt.where(or_(ProjectEntity.name.ilike(term), ProjectEntity.scene_name.ilike(term)))

        is_desc = sort_order.lower() == "desc"
        clean_sort = sort_by.strip()

        # Pure SQL column sorting
        if clean_sort == "name":
            col = ProjectEntity.name
        elif clean_sort in ("createdAt", "created_at"):
            col = ProjectEntity.created_at
        elif clean_sort in ("roomCount", "room_count"):
            col = ProjectEntity.room_count
        else:
            col = ProjectEntity.updated_at

        stmt = stmt.order_by(col.desc() if is_desc else col.asc()).limit(limit).offset(offset)
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
