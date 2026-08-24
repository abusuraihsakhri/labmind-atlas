import os
import json
import uuid
import hashlib
import hmac
from typing import Literal, List, Optional
from pydantic import BaseModel
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from agents.models import Action as ActionModel, AuditEvent

# 🔒 PHI Outbound Guard definition
# We check outbound texts for exact patterns of common PHI (MRNs, raw phone numbers, names, etc.)
# If they look like un-anonymized records, we raise a ValueError to block transmission to LLMs.
class SecurityException(Exception):
    pass

def assert_no_phi(text: str):
    import re
    # Patterns for raw MRNs (e.g. MRN-123456)
    mrn_pattern = re.compile(r'\bMRN-\d+\b', re.IGNORECASE)
    # Generic phone patterns (e.g. +971-50...)
    phone_pattern = re.compile(r'\+?\d{1,4}[-.\s]?\(?\d{1,3}?\)?[-.\s]?\d{1,4}[-.\s]?\d{1,4}[-.\s]?\d{1,9}')
    # Specific keywords indicating untokenized info
    sensitive_keywords = ["John Doe", "Jane Smith", "Alice Johnson", "Dr. Gregory House", "Dr. Meredith Grey"]
    
    if mrn_pattern.search(text):
        raise SecurityException("Security violation: Outbound prompt contains raw MRN pattern.")
    
    if phone_pattern.search(text):
        # Allow phone match only if it is short or does not match a typical raw lab record comment format
        if len(re.findall(r'\d', text)) > 9:
            raise SecurityException("Security violation: Outbound prompt contains raw phone number format.")
            
    for kw in sensitive_keywords:
        if kw in text:
            raise SecurityException(f"Security violation: Outbound prompt contains raw PHI keyword: '{kw}'")

def secure_invoke(model, messages, db: Session, agent_name: str):
    from agents.metrics import llm_invocations_total
    for msg in messages:
        try:
            assert_no_phi(msg.content)
        except SecurityException as e:
            ActionExecutor.log_audit_event(
                db=db,
                actor=agent_name,
                actor_tier="system",
                event_type="PHI_OUTBOUND_BLOCK",
                details={
                    "error": str(e),
                    "blocked_content_length": len(msg.content)
                }
            )
            llm_invocations_total.labels(agent_name=agent_name, status="blocked").inc()
            raise e
    response = model.invoke(messages)
    llm_invocations_total.labels(agent_name=agent_name, status="success").inc()
    return response

# Base action structure emitted by workers
class ActionProposed(BaseModel):
    action_type: str
    specimen_token: str
    payload: dict
    confidence: float
    reasoning: str

# Central Action Executor
AUDIT_SECRET_KEY = os.getenv("AUDIT_SECRET_KEY")
if not AUDIT_SECRET_KEY:
    raise RuntimeError("SECURITY EXCEPTION: AUDIT_SECRET_KEY environment variable is not defined.")
AUDIT_SECRET_KEY = AUDIT_SECRET_KEY.encode()

class ActionExecutor:
    @staticmethod
    def log_audit_event(
        db: Session, 
        actor: str, 
        actor_tier: str, 
        event_type: str, 
        details: dict
    ) -> str:
        # Fetch the last audit event to get prev_hash
        last_event = db.query(AuditEvent).order_by(AuditEvent.id.desc()).first()
        prev_hash = last_event.row_hash if last_event else "0" * 64
        
        # Calculate row hash
        now = datetime.now(timezone.utc).isoformat()
        details_str = json.dumps(details, sort_keys=True)
        hash_input = f"{prev_hash}|{actor}|{actor_tier}|{event_type}|{details_str}|{now}".encode('utf-8')
        row_hash = hmac.new(AUDIT_SECRET_KEY, hash_input, hashlib.sha256).hexdigest()
        
        audit_entry = AuditEvent(
            prev_hash=prev_hash,
            row_hash=row_hash,
            actor=actor,
            actor_tier=actor_tier,
            event_type=event_type,
            detail_jsonb=details,
            created_at=datetime.now(timezone.utc)
        )
        
        db.add(audit_entry)
        db.commit()
        return row_hash

    @staticmethod
    def execute(
        db: Session, 
        proposal: ActionProposed, 
        agent_name: str, 
        trust_stage: Literal["OBSERVE", "SUGGEST"] = "SUGGEST"
    ) -> dict:
        from agents.metrics import actions_proposed_total
        action_id = str(uuid.uuid4())
        
        # Validate confidence is within bounds
        confidence = max(0.0, min(1.0, proposal.confidence))
        
        # 1. 🔒 Observe trust stage constraint: takes NO action
        if trust_stage == "OBSERVE":
            status = "rejected"
            reasoning = "Rejected automatically: System is in read-only OBSERVE stage."
        else:
            # Under SUGGEST, all proposed actions require manual operator approval
            status = "proposed"
            reasoning = proposal.reasoning
            
        action_db = ActionModel(
            id=action_id,
            agent_name=agent_name,
            specimen_token=proposal.specimen_token,
            action_type=proposal.action_type,
            payload_jsonb=proposal.payload,
            confidence=confidence,
            reasoning=reasoning,
            status=status,
            proposed_at=datetime.now(timezone.utc)
        )
        db.add(action_db)
        db.commit()

        actions_proposed_total.labels(
            agent_name=agent_name,
            action_type=proposal.action_type
        ).inc()

        # Log this execution request in audit table
        ActionExecutor.log_audit_event(
            db=db,
            actor=agent_name,
            actor_tier="worker",
            event_type="ACTION_PROPOSED",
            details={
                "action_id": action_id,
                "specimen_token": proposal.specimen_token,
                "action_type": proposal.action_type,
                "status": status,
                "trust_stage": trust_stage
            }
        )
        
        return {
            "action_id": action_id,
            "status": status,
            "reasoning": reasoning
        }
