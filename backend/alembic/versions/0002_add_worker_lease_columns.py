"""add worker lease and completion columns

Revision ID: 0002_worker_lease
Revises: 0001_initial
Create Date: 2026-10-24 16:58:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0002_worker_lease"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {c["name"] for c in inspector.get_columns("articles")}
    indexes = {i["name"] for i in inspector.get_indexes("articles")}

    # Add locked_at for lease-based crash recovery
    if "locked_at" not in columns:
        op.add_column("articles", sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True))
    if "ix_articles_locked_at" not in indexes:
        op.create_index("ix_articles_locked_at", "articles", ["locked_at"])

    # Add completed_at for completion tracking
    if "completed_at" not in columns:
        op.add_column("articles", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    if "ix_articles_completed_at" not in indexes:
        op.create_index("ix_articles_completed_at", "articles", ["completed_at"])


def downgrade() -> None:
    op.drop_index("ix_articles_completed_at", table_name="articles")
    op.drop_column("articles", "completed_at")
    op.drop_index("ix_articles_locked_at", table_name="articles")
    op.drop_column("articles", "locked_at")
