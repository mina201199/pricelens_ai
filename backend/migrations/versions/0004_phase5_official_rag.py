"""Add official document storage and pgvector retrieval for Phase 5.

Revision ID: 0004_phase5
Revises: 0003_phase4
Create Date: 2026-09-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0004_phase5"
down_revision: str | None = "0003_phase4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE SCHEMA IF NOT EXISTS rag")
    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("published_at", sa.Date(), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("product_slugs", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("event_start", sa.Date(), nullable=False),
        sa.Column("event_end", sa.Date(), nullable=False),
        sa.Column(
            "metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint("event_end >= event_start", name="valid_event_window"),
        sa.PrimaryKeyConstraint("id", name="pk_documents"),
        sa.UniqueConstraint("source_url", name="uq_documents_source_url"),
        schema="rag",
    )
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("document_id", sa.BigInteger(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(256), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"], ["rag.documents.id"], ondelete="CASCADE",
            name="fk_document_chunks_document_id_documents",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_document_chunks"),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_document_chunk_index"),
        schema="rag",
    )
    op.create_index(
        "ix_rag_document_chunks_document_id", "document_chunks", ["document_id"],
        schema="rag",
    )
    op.create_index(
        "ix_rag_document_chunks_embedding_hnsw", "document_chunks", ["embedding"],
        schema="rag", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(
        "ix_rag_documents_product_event", "documents",
        ["product_slugs"], schema="rag", postgresql_using="gin",
    )
    op.create_index(
        "ix_rag_documents_published_at", "documents", ["published_at"], schema="rag"
    )


def downgrade() -> None:
    op.drop_index("ix_rag_documents_published_at", table_name="documents", schema="rag")
    op.drop_index("ix_rag_documents_product_event", table_name="documents", schema="rag")
    op.drop_index(
        "ix_rag_document_chunks_embedding_hnsw", table_name="document_chunks", schema="rag"
    )
    op.drop_index(
        "ix_rag_document_chunks_document_id", table_name="document_chunks", schema="rag"
    )
    op.drop_table("document_chunks", schema="rag")
    op.drop_table("documents", schema="rag")
    op.execute("DROP SCHEMA rag")
    op.execute("DROP EXTENSION vector")
