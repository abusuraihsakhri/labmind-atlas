from sqlalchemy import Column, String, Integer, DateTime, Boolean, Numeric, BigInteger, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from .database import Base
import datetime

class SpecimenEvent(Base):
    __tablename__ = "specimen_events"
    id = Column(UUID(as_uuid=True), primary_key=True)
    specimen_token = Column(String(255), nullable=False, index=True)
    event_type = Column(String(100), nullable=False)
    test_code = Column(String(100), nullable=False)
    status = Column(String(100), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=False)
    anon_clinician_token = Column(String(255), nullable=False)
    meta_jsonb = Column(JSONB)

class SpecimenState(Base):
    __tablename__ = "specimen_state"
    specimen_token = Column(String(255), primary_key=True)
    current_status = Column(String(100), nullable=False)
    accessioned_at = Column(DateTime(timezone=True), nullable=False)
    expected_signout_at = Column(DateTime(timezone=True), nullable=False)
    tat_risk_level = Column(String(50), nullable=False)
    last_event_at = Column(DateTime(timezone=True), nullable=False)

class EpisodicMemory(Base):
    __tablename__ = "episodic_memory"
    id = Column(UUID(as_uuid=True), primary_key=True)
    specimen_token = Column(String(255), nullable=False, index=True)
    summary_text = Column(Text, nullable=False)
    # We will use text or simple arrays if pgvector is not natively loaded as Type, 
    # but pgvector can be mapped via custom vector type or raw SQL. Let's use custom pgvector column representation.
    # In SQLAlchemy we can represent it with a raw type or string. Since SQLAlchemy doesn't have vector by default 
    # unless pgvector library is imported, let's declare custom column type for vector.
    from sqlalchemy.types import UserDefinedType
    class VectorType(UserDefinedType):
        def get_col_spec(self, **kw):
            return "vector(384)"
    
    embedding = Column(VectorType, nullable=False)
    outcome = Column(String(255), nullable=False)
    occurred_at = Column(DateTime(timezone=True), nullable=False)

class SemanticRule(Base):
    __tablename__ = "semantic_rules"
    id = Column(UUID(as_uuid=True), primary_key=True)
    rule_type = Column(String(100), nullable=False)
    key = Column(String(255), nullable=False)
    value_jsonb = Column(JSONB, nullable=False)
    version = Column(Integer, nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_to = Column(DateTime(timezone=True))

class Action(Base):
    __tablename__ = "actions"
    id = Column(UUID(as_uuid=True), primary_key=True)
    agent_name = Column(String(100), nullable=False)
    specimen_token = Column(String(255), nullable=False, index=True)
    action_type = Column(String(100), nullable=False)
    payload_jsonb = Column(JSONB)
    confidence = Column(Numeric(3, 2), nullable=False)
    reasoning = Column(Text, nullable=False)
    status = Column(String(50), nullable=False) # proposed, approved, dismissed, executed, rejected
    proposed_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True))
    resolved_by = Column(String(255))

class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(BigInteger, primary_key=True)
    prev_hash = Column(String(64), nullable=False)
    row_hash = Column(String(64), nullable=False)
    actor = Column(String(255), nullable=False)
    actor_tier = Column(String(50), nullable=False)
    event_type = Column(String(100), nullable=False)
    detail_jsonb = Column(JSONB)
    created_at = Column(DateTime(timezone=True), default=datetime.datetime.now)

class CriticalValueEvent(Base):
    __tablename__ = "critical_value_events"
    id = Column(UUID(as_uuid=True), primary_key=True)
    specimen_token = Column(String(255), nullable=False, index=True)
    value_summary = Column(Text, nullable=False)
    routed_to_token = Column(String(255), nullable=False)
    routed_at = Column(DateTime(timezone=True), nullable=False)
    acknowledged_at = Column(DateTime(timezone=True))
    acknowledged_by = Column(String(255))
    escalated = Column(Boolean, default=False)
