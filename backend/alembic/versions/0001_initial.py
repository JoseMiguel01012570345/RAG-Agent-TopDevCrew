"""Esquema inicial: comunidades, documentos y chunks con pgvector.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE users (
            id UUID PRIMARY KEY,
            external_id VARCHAR(120) NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE communities (
            id UUID PRIMARY KEY,
            name VARCHAR(200) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE memberships (
            id UUID PRIMARY KEY,
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            community_id UUID NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
            role VARCHAR(40) NOT NULL DEFAULT 'admin',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (user_id, community_id)
        )
        """
    )
    op.execute("CREATE INDEX ix_memberships_user ON memberships (user_id)")
    op.execute("CREATE INDEX ix_memberships_community ON memberships (community_id)")
    op.execute(
        """
        CREATE TABLE documents (
            id UUID PRIMARY KEY,
            community_id UUID NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
            filename VARCHAR(255) NOT NULL,
            content_type VARCHAR(120) NOT NULL,
            sha256 CHAR(64) NOT NULL,
            content BYTEA NOT NULL,
            status VARCHAR(20) NOT NULL,
            error_code VARCHAR(40),
            error_message TEXT,
            page_count INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_documents_status CHECK (
                status IN ('pending', 'processing', 'ready', 'failed')
            ),
            UNIQUE (community_id, sha256)
        )
        """
    )
    op.execute("CREATE INDEX ix_documents_community ON documents (community_id)")
    op.execute(
        """
        CREATE TABLE chunks (
            id UUID PRIMARY KEY,
            community_id UUID NOT NULL REFERENCES communities(id) ON DELETE CASCADE,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            page INTEGER NOT NULL,
            chunk_index INTEGER NOT NULL,
            text TEXT NOT NULL,
            embedding vector(384) NOT NULL,
            tsv tsvector GENERATED ALWAYS AS (to_tsvector('spanish', text)) STORED,
            UNIQUE (document_id, chunk_index)
        )
        """
    )
    op.execute("CREATE INDEX ix_chunks_community ON chunks (community_id)")
    op.execute("CREATE INDEX ix_chunks_tsv ON chunks USING gin (tsv)")
    op.execute(
        "CREATE INDEX ix_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS memberships")
    op.execute("DROP TABLE IF EXISTS communities")
    op.execute("DROP TABLE IF EXISTS users")
