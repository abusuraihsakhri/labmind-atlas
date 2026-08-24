"""initial schema

Revision ID: 001_initial
Revises:
Create Date: 2026-08-24
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "specimen_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("specimen_token", sa.String(255), nullable=False, index=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("test_code", sa.String(100), nullable=False),
        sa.Column("status", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("anon_clinician_token", sa.String(255), nullable=False),
        sa.Column("meta_jsonb", JSONB),
    )

    op.create_table(
        "specimen_state",
        sa.Column("specimen_token", sa.String(255), primary_key=True),
        sa.Column("current_status", sa.String(100), nullable=False),
        sa.Column("accessioned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expected_signout_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tat_risk_level", sa.String(50), nullable=False),
        sa.Column("last_event_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "semantic_rules",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("rule_type", sa.String(100), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value_jsonb", JSONB, nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
    )

    op.create_table(
        "actions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("specimen_token", sa.String(255), nullable=False, index=True),
        sa.Column("action_type", sa.String(100), nullable=False),
        sa.Column("payload_jsonb", JSONB),
        sa.Column("confidence", sa.Numeric(3, 2), nullable=False),
        sa.Column("reasoning", sa.Text, nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("proposed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.String(255)),
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("row_hash", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("actor_tier", sa.String(50), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("detail_jsonb", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "critical_value_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("specimen_token", sa.String(255), nullable=False, index=True),
        sa.Column("value_summary", sa.Text, nullable=False),
        sa.Column("routed_to_token", sa.String(255), nullable=False),
        sa.Column("routed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by", sa.String(255)),
        sa.Column("escalated", sa.Boolean, server_default=sa.text("false")),
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION block_audit_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'Updates and deletions on audit_events are strictly prohibited.';
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trigger_block_audit_mutation
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW
        EXECUTE FUNCTION block_audit_mutation();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trigger_block_audit_mutation ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS block_audit_mutation()")
    op.drop_table("critical_value_events")
    op.drop_table("audit_events")
    op.drop_table("actions")
    op.drop_table("semantic_rules")
    op.drop_table("specimen_state")
    op.drop_table("specimen_events")
