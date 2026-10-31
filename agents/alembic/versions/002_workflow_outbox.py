"""Durable workflow-outbox handoff after specimen ingestion.

Revision ID: 002_workflow_outbox
Revises: 001_initial
"""
from alembic import op

revision = "002_workflow_outbox"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The Compose SQL initializer and Alembic baseline may both be used by
    # development installations; creating this table is intentionally idempotent.
    op.execute("""
        CREATE TABLE IF NOT EXISTS workflow_outbox (
            event_id UUID PRIMARY KEY REFERENCES specimen_events(id) ON DELETE RESTRICT,
            specimen_token VARCHAR(255) NOT NULL,
            clinician_token VARCHAR(255) NOT NULL,
            state_applied BOOLEAN NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at TIMESTAMP WITH TIME ZONE
        );
        CREATE INDEX IF NOT EXISTS idx_workflow_outbox_status_created
            ON workflow_outbox(status, created_at);
        
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS workflow_outbox")
