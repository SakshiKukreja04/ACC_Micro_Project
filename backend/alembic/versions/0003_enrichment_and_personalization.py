"""add AI enrichment columns, bookmarks and reading history

Revision ID: 0003_enrichment
Revises: 0002_worker_lease
Create Date: 2026-10-26 18:00:00.000000

Adds:
  * articles.sentiment / sentiment_score   -> sentiment analysis (VADER + LLM)
  * articles.grounding_score               -> Fact-Grounding score of AI summaries (USP)
  * articles.reading_time_minutes          -> estimated reading time
  * articles.keywords                      -> extracted keywords (trending topic detection)
  * bookmarks                              -> per-reader saved articles (anonymous client id)
  * reading_events                         -> reading history powering "For You" recommendations
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003_enrichment"
down_revision: Union[str, None] = "0002_worker_lease"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_ARTICLE_COLUMNS = [
    ("sentiment", sa.String(length=16)),
    ("sentiment_score", sa.Float()),
    ("grounding_score", sa.Float()),
    ("reading_time_minutes", sa.Integer()),
    ("keywords", sa.JSON()),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing = {c["name"] for c in inspector.get_columns("articles")}
    for name, col_type in NEW_ARTICLE_COLUMNS:
        if name not in existing:
            op.add_column("articles", sa.Column(name, col_type, nullable=True))

    article_indexes = {i["name"] for i in inspector.get_indexes("articles")}
    if "ix_articles_sentiment" not in article_indexes:
        op.create_index("ix_articles_sentiment", "articles", ["sentiment"])

    if not inspector.has_table("bookmarks"):
        op.create_table(
            "bookmarks",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("client_id", sa.String(length=64), nullable=False),
            sa.Column(
                "article_id",
                sa.String(length=36),
                sa.ForeignKey("articles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("client_id", "article_id", name="uq_bookmarks_client_article"),
        )
        op.create_index("ix_bookmarks_client_id", "bookmarks", ["client_id"])

    if not inspector.has_table("reading_events"):
        op.create_table(
            "reading_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("client_id", sa.String(length=64), nullable=False),
            sa.Column(
                "article_id",
                sa.String(length=36),
                sa.ForeignKey("articles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("event_type", sa.String(length=24), nullable=False, server_default="view"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_reading_events_client_created", "reading_events", ["client_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_reading_events_client_created", table_name="reading_events")
    op.drop_table("reading_events")
    op.drop_index("ix_bookmarks_client_id", table_name="bookmarks")
    op.drop_table("bookmarks")
    op.drop_index("ix_articles_sentiment", table_name="articles")
    for name, _ in reversed(NEW_ARTICLE_COLUMNS):
        op.drop_column("articles", name)
