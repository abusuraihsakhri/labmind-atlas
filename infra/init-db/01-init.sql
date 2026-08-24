-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. De-identified specimen event stream (episodic source)
CREATE TABLE IF NOT EXISTS specimen_events (
    id UUID PRIMARY KEY,
    specimen_token VARCHAR(255) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    test_code VARCHAR(100) NOT NULL,
    status VARCHAR(100) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE NOT NULL,
    anon_clinician_token VARCHAR(255) NOT NULL,
    meta_jsonb JSONB
);

-- Index for fast lookup by specimen_token
CREATE INDEX IF NOT EXISTS idx_specimen_events_token ON specimen_events(specimen_token);

-- 2. Working memory snapshot durable mirror
CREATE TABLE IF NOT EXISTS specimen_state (
    specimen_token VARCHAR(255) PRIMARY KEY,
    current_status VARCHAR(100) NOT NULL,
    accessioned_at TIMESTAMP WITH TIME ZONE NOT NULL,
    expected_signout_at TIMESTAMP WITH TIME ZONE NOT NULL,
    tat_risk_level VARCHAR(50) NOT NULL, -- green, yellow, red
    last_event_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- 3. Episodic embeddings for recall
CREATE TABLE IF NOT EXISTS episodic_memory (
    id UUID PRIMARY KEY,
    specimen_token VARCHAR(255) NOT NULL,
    summary_text TEXT NOT NULL,
    embedding vector(384) NOT NULL, -- dimension 384 for sentence-transformers/all-MiniLM-L6-v2
    outcome VARCHAR(255) NOT NULL,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_episodic_memory_token ON episodic_memory(specimen_token);
CREATE INDEX IF NOT EXISTS idx_episodic_embedding ON episodic_memory USING hnsw (embedding vector_cosine_ops);

-- 4. Semantic memory (SOPs, ranges) - versioned
CREATE TABLE IF NOT EXISTS semantic_rules (
    id UUID PRIMARY KEY,
    rule_type VARCHAR(100) NOT NULL,
    key VARCHAR(255) NOT NULL,
    value_jsonb JSONB NOT NULL,
    version INT NOT NULL,
    valid_from TIMESTAMP WITH TIME ZONE NOT NULL,
    valid_to TIMESTAMP WITH TIME ZONE
);

-- 5. Proposed + executed actions
CREATE TABLE IF NOT EXISTS actions (
    id UUID PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    specimen_token VARCHAR(255) NOT NULL,
    action_type VARCHAR(100) NOT NULL,
    payload_jsonb JSONB,
    confidence NUMERIC(3, 2) NOT NULL,
    reasoning TEXT NOT NULL,
    status VARCHAR(50) NOT NULL, -- proposed, approved, dismissed, executed, rejected
    proposed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    resolved_at TIMESTAMP WITH TIME ZONE,
    resolved_by VARCHAR(255)
);

CREATE INDEX IF NOT EXISTS idx_actions_token ON actions(specimen_token);

-- 6. 🔒 Append-only, hash-chained audit events
CREATE TABLE IF NOT EXISTS audit_events (
    id BIGSERIAL PRIMARY KEY,
    prev_hash VARCHAR(64) NOT NULL,
    row_hash VARCHAR(64) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    actor_tier VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    detail_jsonb JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Critical value acknowledgement loop (jailed, 10y retention)
CREATE TABLE IF NOT EXISTS critical_value_events (
    id UUID PRIMARY KEY,
    specimen_token VARCHAR(255) NOT NULL,
    value_summary TEXT NOT NULL,
    routed_to_token VARCHAR(255) NOT NULL,
    routed_at TIMESTAMP WITH TIME ZONE NOT NULL,
    acknowledged_at TIMESTAMP WITH TIME ZONE,
    acknowledged_by VARCHAR(255),
    escalated BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_critical_value_token ON critical_value_events(specimen_token);


-- 🔒 SECURITY POLICIES & CONTROLS

-- Trigger to strictly block updates or deletions on audit_events
CREATE OR REPLACE FUNCTION block_audit_mutation()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Updates and deletions on audit_events are strictly prohibited by system security configuration.';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_block_audit_mutation
BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW
EXECUTE FUNCTION block_audit_mutation();
