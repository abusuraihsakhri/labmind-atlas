"""Durable bounded retry and redacted dead-letter diagnostics."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert as pg_insert

from agents.database import SessionLocal
from agents.models import StreamFailure, WorkflowOutbox

MAX_ATTEMPTS = 5
BASE_DELAY_SECONDS = 2
MAX_DELAY_SECONDS = 300


def retry_delay(attempts: int) -> timedelta:
    return timedelta(seconds=min(MAX_DELAY_SECONDS, BASE_DELAY_SECONDS * 2 ** (attempts - 1)))


def stream_retry_state(stream_id: str, now=None) -> str:
    """Return 'ready', 'defer', or 'dead_letter' (no raw payload persisted)."""
    now = now or datetime.now(timezone.utc)
    with SessionLocal() as db:
        record = db.get(StreamFailure, stream_id)
        if record is None:
            return "ready"
        if record.status == "dead_letter":
            return "dead_letter"
        return "defer" if record.next_attempt_at > now else "ready"


def record_stream_failure(stream_id: str, payload_hash: str, error: Exception) -> str:
    """Persist diagnostics *before* a poison message can be XACKed."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        with db.begin():
            db.execute(
                pg_insert(StreamFailure)
                .values(
                    stream_id=stream_id,
                    attempts=0,
                    status="pending",
                    error_code=type(error).__name__[:100],
                    payload_sha256=payload_hash,
                    next_attempt_at=now,
                )
                .on_conflict_do_nothing(index_elements=[StreamFailure.stream_id])
            )
            item = db.get(StreamFailure, stream_id, with_for_update=True)
            item.attempts += 1
            item.error_code = type(error).__name__[:100]
            item.payload_sha256 = payload_hash
            if item.attempts >= MAX_ATTEMPTS:
                item.status = "dead_letter"
                item.dead_lettered_at = now
            else:
                item.status = "pending"
                item.next_attempt_at = now + retry_delay(item.attempts)
            return item.status


def record_stream_success(stream_id: str) -> None:
    """Preserve resolved retry diagnostics for audit/reconciliation."""
    with SessionLocal() as db:
        with db.begin():
            item = db.get(StreamFailure, stream_id, with_for_update=True)
            if item and item.status != "dead_letter":
                item.status = "resolved"


def record_outbox_failure(event_id, error: Exception) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        with db.begin():
            row = db.get(WorkflowOutbox, event_id, with_for_update=True)
            if row is None or row.status != "pending":
                return
            row.attempts += 1
            row.last_error = type(error).__name__[:100]
            if row.attempts >= MAX_ATTEMPTS:
                row.status = "dead_letter"
            else:
                row.next_attempt_at = now + retry_delay(row.attempts)
