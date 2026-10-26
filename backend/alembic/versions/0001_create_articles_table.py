"""create articles table

Revision ID: 0001_initial
Revises: 
Create Date: 2026-10-24 16:25:00.000000

"""
from typing import Sequence, Union
from alembic import op
# pyrefly: ignore[missing-import]
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: services may have created the table via create_all() before migrations ran
    if sa.inspect(op.get_bind()).has_table("articles"):
        return
    op.create_table(
        "articles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("canonical_url", sa.Text(), nullable=False),
        sa.Column("source_name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("processing_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("key_takeaways", sa.JSON(), nullable=True),
        sa.Column("cluster_id", sa.String(length=64), nullable=True),
        sa.Column("raw_metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_articles"),
        sa.UniqueConstraint("canonical_url", name="uq_articles_canonical_url"),
        sa.UniqueConstraint("content_hash", name="uq_articles_content_hash"),
    )

    op.create_index("ix_articles_canonical_url", "articles", ["canonical_url"])
    op.create_index("ix_articles_content_hash", "articles", ["content_hash"])
    op.create_index("ix_articles_source_name", "articles", ["source_name"])
    op.create_index("ix_articles_category", "articles", ["category"])
    op.create_index("ix_articles_published_at", "articles", ["published_at"])
    op.create_index("ix_articles_collected_at", "articles", ["collected_at"])
    op.create_index("ix_articles_processing_status", "articles", ["processing_status"])
    op.create_index("ix_articles_cluster_id", "articles", ["cluster_id"])
    op.create_index("ix_articles_status_collected", "articles", ["processing_status", "collected_at"])
    op.create_index("ix_articles_category_published", "articles", ["category", "published_at"])


def downgrade() -> None:
    op.drop_index("ix_articles_category_published", table_name="articles")
    op.drop_index("ix_articles_status_collected", table_name="articles")
    op.drop_index("ix_articles_cluster_id", table_name="articles")
    op.drop_index("ix_articles_processing_status", table_name="articles")
    op.drop_index("ix_articles_collected_at", table_name="articles")
    op.drop_index("ix_articles_published_at", table_name="articles")
    op.drop_index("ix_articles_category", table_name="articles")
    op.drop_index("ix_articles_source_name", table_name="articles")
    op.drop_index("ix_articles_content_hash", table_name="articles")
    op.drop_index("ix_articles_canonical_url", table_name="articles")
    op.drop_table("articles")
