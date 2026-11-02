"""Bounded retry persistence and event quarantine.

Revision ID: 003_retry_recovery
Revises: 002_workflow_outbox
"""
from alembic import op

revision = "003_retry_recovery"
down_revision = "002_workflow_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE workflow_outbox
            ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP;
        CREATE INDEX IF NOT EXISTS idx_workflow_outbox_retry
            ON workflow_outbox(status, next_attempt_at, created_at);

        CREATE TABLE IF NOT EXISTS stream_failures (
            stream_id VARCHAR(100) PRIMARY KEY,
            attempts INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            next_attempt_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            error_code VARCHAR(100) NOT NULL,
            payload_sha256 VARCHAR(64) NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            dead_lettered_at TIMESTAMP WITH TIME ZONE
        );
        CREATE INDEX IF NOT EXISTS idx_stream_failures_status
            ON stream_failures(status, next_attempt_at);

    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_stream_failures_status")
    op.execute("DROP TABLE IF EXISTS stream_failures")
    op.execute("DROP INDEX IF EXISTS idx_workflow_outbox_retry")
    op.execute("ALTER TABLE workflow_outbox DROP COLUMN IF EXISTS next_attempt_at")
