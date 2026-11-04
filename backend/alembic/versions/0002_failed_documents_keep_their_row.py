"""Un documento fallido no ocupa el hash de uno nuevo.

Revision ID: 0002_failed_keep
Revises: 0001_initial
Create Date: 2026-11-04
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_failed_keep"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_community_id_sha256_key")
    op.execute("ALTER TABLE documents DROP CONSTRAINT IF EXISTS uq_document_sha")
    op.execute("DROP INDEX IF EXISTS uq_document_active_sha")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_document_active_sha
        ON documents (community_id, sha256)
        WHERE status <> 'failed'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_document_active_sha")
    op.execute(
        """
        ALTER TABLE documents
        ADD CONSTRAINT documents_community_id_sha256_key UNIQUE (community_id, sha256)
        """
    )
