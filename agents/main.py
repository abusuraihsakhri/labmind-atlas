import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from agents.pipeline import start_pipeline_listener
from agents.database import get_db, SessionLocal
from agents.models import SpecimenState, Action, AuditEvent
from agents.base import ActionExecutor
from pydantic import BaseModel
from datetime import datetime, timezone, timedelta
from typing import Optional
import hmac
import os
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from slowapi import Limiter
from slowapi.util import get_remote_address
import json
import csv
import io
import asyncio
import logging
from fastapi.responses import StreamingResponse

logger = logging.getLogger("labmind.agents")

security = HTTPBearer()

TIER2_AUTH_SECRET = os.getenv("TIER2_AUTH_SECRET")
TIER3_AUTH_SECRET = os.getenv("TIER3_AUTH_SECRET")
SERVICE_AUTH_SECRET = os.getenv("SERVICE_AUTH_SECRET")

if not all([TIER2_AUTH_SECRET, TIER3_AUTH_SECRET, SERVICE_AUTH_SECRET]):
    raise RuntimeError(
        "SECURITY EXCEPTION: TIER2_AUTH_SECRET, TIER3_AUTH_SECRET, "
        "and SERVICE_AUTH_SECRET environment variables must be defined."
    )

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if hmac.compare_digest(token, TIER3_AUTH_SECRET):
        return {"user": "Administrator", "tier": "Tier 3"}
    elif hmac.compare_digest(token, TIER2_AUTH_SECRET):
        return {"user": "Operator", "tier": "Tier 2"}
    elif hmac.compare_digest(token, SERVICE_AUTH_SECRET):
        return {"user": "Service", "tier": "System"}
    logger.warning("Invalid authentication token attempt")
    raise HTTPException(status_code=401, detail="Invalid authentication token")

def require_tier(allowed_tiers: list):
    def role_checker(user: dict = Depends(verify_token)):
        if user["tier"] not in allowed_tiers:
            raise HTTPException(status_code=403, detail="Insufficient privileges")
        return user
    return role_checker

# Thread-safe config for global trust stage (default to SUGGEST)
_config_lock = threading.Lock()
GLOBAL_CONFIG = {
    "trust_stage": "SUGGEST"
}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start Redis Stream listener in background thread
    thread = threading.Thread(target=start_pipeline_listener, daemon=True)
    thread.start()
    yield

app = FastAPI(title="LabMind Cloud Agents Service", lifespan=lifespan)
app.state.limiter = Limiter(key_func=get_remote_address)

from agents.metrics import router as metrics_router
app.include_router(metrics_router)

# Allow CORS for Next.js web app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class StageUpdateRequest(BaseModel):
    stage: str # OBSERVE | SUGGEST

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "agents"}

@app.get("/events/specimens")
async def stream_specimens(user: dict = Depends(require_tier(["Tier 2", "Tier 3"]))):
    async def event_generator():
        last_count = 0
        while True:
            db = SessionLocal()
            try:
                states = db.query(SpecimenState).order_by(SpecimenState.last_event_at.desc()).all()
                data = [{
                    "specimen_token": s.specimen_token,
                    "current_status": s.current_status,
                    "tat_risk_level": s.tat_risk_level,
                    "last_event_at": s.last_event_at.isoformat()
                } for s in states]

                current_count = len(data)
                if current_count != last_count:
                    yield f"data: {json.dumps({'type': 'specimens', 'data': data})}\n\n"
                    last_count = current_count
                else:
                    yield f": keepalive\n\n"
            except Exception as e:
                logger.error("SSE error: %s", e)
            finally:
                db.close()
            await asyncio.sleep(3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@app.get("/specimens")
@limiter.limit("60/minute")
def get_specimens(request: Request, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 2", "Tier 3"]))):
    states = db.query(SpecimenState).order_by(SpecimenState.last_event_at.desc()).all()
    return [{
        "specimen_token": s.specimen_token,
        "current_status": s.current_status,
        "accessioned_at": s.accessioned_at.isoformat(),
        "expected_signout_at": s.expected_signout_at.isoformat(),
        "tat_risk_level": s.tat_risk_level,
        "last_event_at": s.last_event_at.isoformat()
    } for s in states]

@app.get("/actions")
@limiter.limit("60/minute")
def get_actions(request: Request, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 2", "Tier 3"]))):
    actions = db.query(Action).filter(Action.status == "proposed").all()
    return [{
        "id": str(a.id),
        "agent_name": a.agent_name,
        "specimen_token": a.specimen_token,
        "action_type": a.action_type,
        "payload": a.payload_jsonb,
        "confidence": float(a.confidence),
        "reasoning": a.reasoning,
        "status": a.status,
        "proposed_at": a.proposed_at.isoformat()
    } for a in actions]

@app.post("/actions/{action_id}/approve")
@limiter.limit("30/minute")
def approve_action(request: Request, action_id: str, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 2", "Tier 3"]))):
    action = db.query(Action).filter(Action.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    
    action.status = "approved"
    action.resolved_at = datetime.now(timezone.utc)
    action.resolved_by = f"{user['user']} ({user['tier']})"
    db.commit()

    # Log in audit trail
    ActionExecutor.log_audit_event(
        db=db,
        actor=f"{user['user']} ({user['tier']})",
        actor_tier=user['tier'].replace("Tier ", "Tier"),
        event_type="ACTION_APPROVED",
        details={
            "action_id": action_id,
            "specimen_token": action.specimen_token,
            "action_type": action.action_type
        }
    )
    return {"status": "success", "message": "Action approved and logged"}

@app.post("/actions/{action_id}/dismiss")
@limiter.limit("30/minute")
def dismiss_action(request: Request, action_id: str, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 2", "Tier 3"]))):
    action = db.query(Action).filter(Action.id == action_id).first()
    if not action:
        raise HTTPException(status_code=404, detail="Action not found")
    
    action.status = "dismissed"
    action.resolved_at = datetime.now(timezone.utc)
    action.resolved_by = f"{user['user']} ({user['tier']})"
    db.commit()

    # Log in audit trail
    ActionExecutor.log_audit_event(
        db=db,
        actor=f"{user['user']} ({user['tier']})",
        actor_tier=user['tier'].replace("Tier ", "Tier"),
        event_type="ACTION_DISMISSED",
        details={
            "action_id": action_id,
            "specimen_token": action.specimen_token,
            "action_type": action.action_type
        }
    )
    return {"status": "success", "message": "Action dismissed and logged"}

@app.get("/admin/stage")
def get_trust_stage(user: dict = Depends(require_tier(["Tier 2", "Tier 3"]))):
    return {"trust_stage": GLOBAL_CONFIG["trust_stage"]}

@app.post("/admin/stage")
def update_trust_stage(payload: StageUpdateRequest, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 3"]))):
    if payload.stage not in ["OBSERVE", "SUGGEST"]:
        raise HTTPException(status_code=400, detail="Invalid trust stage. Must be OBSERVE or SUGGEST.")
    
    with _config_lock:
        old_stage = GLOBAL_CONFIG["trust_stage"]
        GLOBAL_CONFIG["trust_stage"] = payload.stage
    
    # Log in audit trail
    ActionExecutor.log_audit_event(
        db=db,
        actor=f"{user['user']} ({user['tier']})",
        actor_tier="Administrator",
        event_type="TRUST_STAGE_TRANSITION",
        details={
            "old_stage": old_stage,
            "new_stage": payload.stage
        }
    )
    return {"status": "success", "trust_stage": payload.stage}

@app.post("/alerts/{alert_id}/ack")
def acknowledge_critical_alert(alert_id: str, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 2", "Tier 3"]))):
    from agents.models import CriticalValueEvent
    critical_event = db.query(CriticalValueEvent).filter(CriticalValueEvent.id == alert_id).first()
    if not critical_event:
        raise HTTPException(status_code=404, detail="Critical value alert not found")
        
    critical_event.acknowledged_at = datetime.now(timezone.utc)
    critical_event.acknowledged_by = f"{user['user']} ({user['tier']})"
    db.commit()
    
    # Log in audit trail
    ActionExecutor.log_audit_event(
        db=db,
        actor=f"{user['user']} ({user['tier']})",
        actor_tier=user['tier'].replace("Tier ", "Tier"),
        event_type="CRITICAL_VALUE_ACKNOWLEDGED",
        details={
            "critical_event_id": alert_id,
            "specimen_token": critical_event.specimen_token
        }
    )
    return {"status": "success", "message": "Critical alert acknowledged by operator"}

class ChatRequest(BaseModel):
    question: str

    model_config = {"json_schema_extra": {"example": {"question": "What specimens are at risk?"}}}

@app.post("/supervisor/chat")
@limiter.limit("20/minute")
def supervisor_chat(request: Request, payload: ChatRequest, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 2", "Tier 3"]))):
    from agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent()
    response_text = supervisor.query(payload.question, db)
    return {"response": response_text}

@app.get("/audit")
def get_audit_trail(db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 3"]))):
    events = db.query(AuditEvent).order_by(AuditEvent.id.asc()).all()
    
    verified_chain = True
    prev_hash_tracker = "0" * 64
    serialized_events = []
    
    for e in events:
        # Verify prev_hash matches tracker
        is_valid = (e.prev_hash == prev_hash_tracker)
        if not is_valid:
            verified_chain = False
            
        serialized_events.append({
            "id": e.id,
            "prev_hash": e.prev_hash,
            "row_hash": e.row_hash,
            "actor": e.actor,
            "actor_tier": e.actor_tier,
            "event_type": e.event_type,
            "detail": e.detail_jsonb,
            "created_at": e.created_at.isoformat(),
            "is_valid": is_valid
        })
        prev_hash_tracker = e.row_hash
        
    return {
        "verified_chain": verified_chain,
        "events": serialized_events[::-1]
    }

@app.get("/export/specimens")
@limiter.limit("10/minute")
def export_specimens_csv(request: Request, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 3"]))):
    states = db.query(SpecimenState).order_by(SpecimenState.last_event_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["specimen_token", "current_status", "accessioned_at", "expected_signout_at", "tat_risk_level", "last_event_at"])
    for s in states:
        writer.writerow([
            s.specimen_token, s.current_status, s.accessioned_at.isoformat(),
            s.expected_signout_at.isoformat(), s.tat_risk_level, s.last_event_at.isoformat()
        ])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=specimens_export.csv"}
    )

@app.get("/export/audit")
@limiter.limit("10/minute")
def export_audit_csv(request: Request, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 3"]))):
    events = db.query(AuditEvent).order_by(AuditEvent.id.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "prev_hash", "row_hash", "actor", "actor_tier", "event_type", "created_at"])
    for e in events:
        writer.writerow([e.id, e.prev_hash, e.row_hash, e.actor, e.actor_tier, e.event_type, e.created_at.isoformat()])
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_export.csv"}
    )

class ErasureRequest(BaseModel):
    target_table: str
    target_specimen_token: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None

@app.post("/admin/erasure/request")
def request_erasure(payload: ErasureRequest, db: Session = Depends(get_db), user: dict = Depends(require_tier(["Tier 3"]))):
    target_tbl = payload.target_table.lower()

    # 1. 🔒 Jail Check
    jailed_categories = {"critical_value_events", "audit_events", "erasure_records", "privilege_history"}
    if target_tbl in jailed_categories:
        ActionExecutor.log_audit_event(
            db=db,
            actor=f"{user['user']} ({user['tier']})",
            actor_tier="Administrator",
            event_type="ERASURE_REFUSED_JAILED",
            details={
                "target_table": payload.target_table,
                "reason": "Attempted to erase a jailed category"
            }
        )
        raise HTTPException(
            status_code=400, 
            detail=f"Security exception: Table '{payload.target_table}' is a JAILED category and cannot be erased by any tier."
        )

    # 2. 🔒 Mandatory Retention Cutoff Enforcement (90 Days Minimum)
    retention_cutoff = datetime.now(timezone.utc) - timedelta(days=90)

    if target_tbl == "episodic_memory":
        from agents.models import EpisodicMemory

        # Require at least one scoping parameter (specimen token or start_date)
        if not payload.target_specimen_token and not payload.start_date:
            raise HTTPException(
                status_code=400,
                detail="Security exception: Must specify target_specimen_token or start_date to prevent mass deletion."
            )

        # Deletions can only ever target records older than retention cutoff
        query = db.query(EpisodicMemory).filter(EpisodicMemory.occurred_at <= retention_cutoff)

        if payload.target_specimen_token:
            query = query.filter(EpisodicMemory.specimen_token == payload.target_specimen_token)

        if payload.start_date:
            try:
                start_dt = datetime.fromisoformat(payload.start_date)
                if start_dt > retention_cutoff:
                    ActionExecutor.log_audit_event(
                        db=db,
                        actor=f"{user['user']} ({user['tier']})",
                        actor_tier="Administrator",
                        event_type="ERASURE_REFUSED_RETENTION",
                        details={
                            "target_table": payload.target_table,
                            "reason": "Requested start date falls within statutory 90-day retention minimum"
                        }
                    )
                    raise HTTPException(
                        status_code=400,
                        detail="Security exception: Requested timeframe violates the 90-day episodic memory retention policy."
                    )
                query = query.filter(EpisodicMemory.occurred_at >= start_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid start_date format. Use ISO-8601.")

        if payload.end_date:
            try:
                end_dt = datetime.fromisoformat(payload.end_date)
                if end_dt > retention_cutoff:
                    end_dt = retention_cutoff
                query = query.filter(EpisodicMemory.occurred_at <= end_dt)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid end_date format. Use ISO-8601.")

        # 3. Log pre-erasure audit record
        ActionExecutor.log_audit_event(
            db=db,
            actor=f"{user['user']} ({user['tier']})",
            actor_tier="Administrator",
            event_type="ERASURE_INITIATED",
            details={
                "target_table": payload.target_table,
                "specimen_token": payload.target_specimen_token
            }
        )

        try:
            deleted_count = query.delete(synchronize_session=False)
            db.commit()

            # 4. Log completion
            ActionExecutor.log_audit_event(
                db=db,
                actor=f"{user['user']} ({user['tier']})",
                actor_tier="Administrator",
                event_type="ERASURE_COMPLETED",
                details={
                    "target_table": payload.target_table,
                    "deleted_count": deleted_count
                }
            )
            return {"status": "success", "message": f"Successfully erased {deleted_count} eligible records from episodic memory."}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported table target for erasure: '{payload.target_table}'")






