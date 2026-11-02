"""Idempotent, transaction-bound internal outbox processing.

No external notification is permitted here. Critical-like free text becomes
review-only; numeric critical thresholds and clinical routing remain disabled.
"""
import logging
import re
import threading
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from agents.base import ActionExecutor
from agents.database import SessionLocal
from agents.models import Action, SpecimenEvent, SpecimenState, WorkflowOutbox
from agents.retry import record_outbox_failure

logger = logging.getLogger("labmind.outbox")
BATCH_SIZE = 10


def _create_action(db, job, kind, payload, confidence, reasoning, trust_stage):
    action_id = uuid5(NAMESPACE_URL, f"labmind:{job.event_id}:{kind}")
    if db.get(Action, action_id) is not None:
        return
    status = "proposed" if trust_stage == "SUGGEST" else "rejected"
    db.add(
        Action(
            id=action_id,
            agent_name="TAT_Monitor" if kind == "TAT_DELAY_ALERT" else "Critical_Value_Router",
            specimen_token=job.specimen_token,
            action_type=kind,
            payload_jsonb=payload,
            confidence=confidence,
            reasoning=reasoning if status == "proposed" else "OBSERVE: internal review only",
            status=status,
            proposed_at=datetime.now(timezone.utc),
        )
    )
    db.flush()
    ActionExecutor.log_audit_event(
        db,
        actor="WorkflowOutbox",
        actor_tier="worker",
        event_type="ACTION_PROPOSED",
        details={
            "action_id": str(action_id),
            "source_event_id": str(job.event_id),
            "specimen_token": job.specimen_token,
            "action_type": kind,
            "status": status,
            "trust_stage": trust_stage,
        },
        commit=False,
    )


def process_outbox_event(db, job, trust_stage="OBSERVE", now=None):
    """Complete an outbox row atomically with internal actions and audit entries."""
    now = now or datetime.now(timezone.utc)
    source = db.get(SpecimenEvent, job.event_id)
    state = db.get(SpecimenState, job.specimen_token)
    if source is None or state is None:
        raise ValueError("Outbox source or specimen state missing")

    # Superseded events still remain in source history, but cannot emit old
    # workflow proposals after a newer state has already arrived.
    if not job.state_applied or state.last_event_at != source.occurred_at:
        job.status = "completed"
        job.processed_at = now
        return

    if state.current_status == "SIGNED_OUT":
        risk = "green"
    else:
        minutes = (state.expected_signout_at - now).total_seconds() / 60
        risk = "red" if minutes < 0 else "yellow" if minutes < 15 else "green"
    state.tat_risk_level = risk

    if risk != "green":
        _create_action(
            db, job, "TAT_DELAY_ALERT",
            {"risk_level": risk, "expected_signout": state.expected_signout_at.isoformat()},
            0.95 if risk == "red" else 0.85,
            f"Synthetic prototype TAT {risk} from configured nominal target.",
            trust_stage,
        )

    # Free-text detection is deliberately only an internal review flag;
    # no clinician notification, routed critical-value row, or external call.
    comments = (source.meta_jsonb or {}).get("comments", "")
    if comments and re.search(
        r"critical value|panic|potassium level measured at|platelet count critical|malignant neoplasm",
        comments,
        flags=re.IGNORECASE,
    ):
        _create_action(
            db, job, "REVIEW_UNVERIFIED_CRITICAL_SIGNAL",
            {"validation_status": "unverified_free_text", "dispatch_allowed": False,
             "source_event_id": str(job.event_id)},
            0.50,
            "Unverified critical-like comment requires human review, not routing.",
            trust_stage,
        )

    job.status = "completed"
    job.processed_at = now


def run_outbox_batch(session_factory=SessionLocal, trust_stage="OBSERVE", limit=BATCH_SIZE):
    """Process pending jobs without duplicate actions after crashes/restarts."""
    now = datetime.now(timezone.utc)
    with session_factory() as db:
        # Candidate IDs are only a hint; re-check under row lock below.
        candidates = db.scalars(
            select(WorkflowOutbox.event_id)
            .where(WorkflowOutbox.status == "pending",
                   WorkflowOutbox.next_attempt_at <= now)
            .order_by(WorkflowOutbox.created_at, WorkflowOutbox.event_id)
            .limit(limit)
        ).all()
        db.rollback()

    completed = 0
    for event_id in candidates:
        try:
            with session_factory() as db:
                with db.begin():
                    row = db.scalar(
                        select(WorkflowOutbox)
                        .where(WorkflowOutbox.event_id == event_id)
                        .with_for_update(skip_locked=True)
                    )
                    if row is None or row.status != "pending":
                        continue
                    if row.next_attempt_at > datetime.now(timezone.utc):
                        continue
                    process_outbox_event(db, row, trust_stage=trust_stage)
                completed += 1
        except Exception as exc:
            logger.error("Outbox event %s failed (%s)", event_id, type(exc).__name__)
            # A failure recording error is surfaced; no partial work was committed.
            record_outbox_failure(event_id, exc)
    return completed


def start_outbox_worker(stop_event: threading.Event, interval_seconds=2):
    logger.info("Starting internal-only workflow outbox dispatcher")
    while not stop_event.is_set():
        try:
            # A separately approved policy must enable any external routing.
            from agents.main import GLOBAL_CONFIG

            stage = GLOBAL_CONFIG.get("trust_stage", "OBSERVE")
            if stage not in ("OBSERVE", "SUGGEST"):
                stage = "OBSERVE"
            run_outbox_batch(trust_stage=stage)
        except Exception:
            logger.exception("Outbox dispatch loop error")
        stop_event.wait(interval_seconds)
