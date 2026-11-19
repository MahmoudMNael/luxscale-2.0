"""add_project_ownership_and_storage_keys

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-11-19 14:20:00.000000

"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add storage key columns
    op.add_column('projects', sa.Column('thumbnail_object_key', sa.String(length=1024), nullable=True))
    op.add_column('projects', sa.Column('archive_object_key', sa.String(length=1024), nullable=True))

    # 2. Add user_id column as nullable initially for backfill
    op.add_column('projects', sa.Column('user_id', sa.Uuid(), nullable=True))

    # 3. Create a default system admin user if any existing projects need an owner
    conn = op.get_bind()
    projects_count = conn.execute(sa.text("SELECT count(*) FROM projects WHERE user_id IS NULL")).scalar()
    if projects_count and projects_count > 0:
        existing_user = conn.execute(sa.text("SELECT id FROM users LIMIT 1")).scalar()
        if not existing_user:
            default_user_id = str(uuid.uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, email, name, role, created_at, updated_at) "
                    "VALUES (:id, 'admin@lxscale.local', 'System Admin', 'admin', now(), now())"
                ),
                {"id": default_user_id},
            )
            owner_id = default_user_id
        else:
            owner_id = str(existing_user)

        conn.execute(
            sa.text("UPDATE projects SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": owner_id},
        )

    # 4. Enforce NOT NULL and Foreign Key Constraint on user_id
    op.alter_column('projects', 'user_id', nullable=False)
    op.create_index(op.f('ix_projects_user_id'), 'projects', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_projects_user_id_users',
        'projects',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    op.drop_constraint('fk_projects_user_id_users', 'projects', type_='foreignkey')
    op.drop_index(op.f('ix_projects_user_id'), table_name='projects')
    op.drop_column('projects', 'user_id')
    op.drop_column('projects', 'archive_object_key')
    op.drop_column('projects', 'thumbnail_object_key')
