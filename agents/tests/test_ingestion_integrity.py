"""PostgreSQL integration tests for atomic specimen-event ingestion."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import sessionmaker

from agents.ingestion import ConflictingEventId, process_stream_event
from agents.models import SpecimenEvent, SpecimenState, WorkflowOutbox

URL = os.getenv("LABMIND_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Requires LABMIND_TEST_DATABASE_URL (PostgreSQL)")


@pytest.fixture(scope="module")
def sessions():
    if not URL:
        pytest.skip("No PostgreSQL test database")
    engine = create_engine(URL, pool_pre_ping=True)
    factory = sessionmaker(bind=engine, autoflush=False)
    yield factory
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables(sessions):
    with sessions().bind.begin() as connection:
        connection.execute(text("TRUNCATE workflow_outbox, specimen_state, specimen_events CASCADE"))
    yield


def sample_event(*, event_id=None, status="ORDERED", occurred_at=None, token="SPECIMEN_synthetic"):
    timestamp = occurred_at or datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
    return {
        "event_id": str(event_id or uuid4()),
        "specimen_token": token,
        "event_type": "ORDER_PLACED",
        "test_code": "CHEM-20",
        "status": status,
        "occurred_at": timestamp.isoformat(),
        "received_at": (timestamp + timedelta(minutes=1)).isoformat(),
        "clinician_token": "CLINICIAN_synthetic",
        "de_identified_comments": "Synthetic test only",
    }


def count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_one_commit_creates_event_state_and_pending_outbox(sessions):
    payload = sample_event()
    with sessions() as db:
        result = process_stream_event(payload, db)
        assert not result.duplicate
        assert result.state_applied
        assert count(db, SpecimenEvent) == 1
        assert count(db, SpecimenState) == 1
        assert count(db, WorkflowOutbox) == 1
        queued = db.get(WorkflowOutbox, result.event_id)
        assert queued.status == "pending"
        assert queued.state_applied is True


def test_identical_replay_is_safe_even_if_gateway_received_at_changes(sessions):
    payload = sample_event()
    with sessions() as db:
        first = process_stream_event(payload, db)
        retried = dict(payload, received_at="2026-11-01T10:00:00+00:00")
        second = process_stream_event(retried, db)
        assert not first.duplicate
        assert second.duplicate
        assert count(db, SpecimenEvent) == 1
        assert count(db, WorkflowOutbox) == 1


def test_conflicting_duplicate_id_is_never_silently_accepted(sessions):
    payload = sample_event()
    with sessions() as db:
        process_stream_event(payload, db)
        with pytest.raises(ConflictingEventId):
            process_stream_event(dict(payload, status="SIGNED_OUT"), db)
        assert db.get(SpecimenState, payload["specimen_token"]).current_status == "ORDERED"
        assert count(db, WorkflowOutbox) == 1


def test_stale_and_equal_timestamp_events_cannot_regress_state(sessions):
    now = datetime(2026, 10, 30, 15, tzinfo=timezone.utc)
    with sessions() as db:
        newest = process_stream_event(sample_event(status="SIGNED_OUT", occurred_at=now), db)
        old = process_stream_event(
            sample_event(status="PROCESSING", occurred_at=now - timedelta(hours=1)), db
        )
        equal = process_stream_event(sample_event(status="ORDERED", occurred_at=now), db)
        assert newest.state_applied
        assert not old.state_applied
        assert not equal.state_applied
        state = db.get(SpecimenState, "SPECIMEN_synthetic")
        db.refresh(state)
        assert state.current_status == "SIGNED_OUT"
        assert state.last_event_at == now
        assert count(db, SpecimenEvent) == 3
        assert count(db, WorkflowOutbox) == 3


def test_atomic_rollback_when_outbox_flush_fails(sessions):
    payload = sample_event()
    with sessions() as db:
        def fail_outbox_flush(_session, _flush_context, _instances):
            raise RuntimeError("injected outbox persistence failure")

        event.listen(db, "before_flush", fail_outbox_flush)
        with pytest.raises(RuntimeError, match="injected outbox"):
            process_stream_event(payload, db)
        event.remove(db, "before_flush", fail_outbox_flush)

    with sessions() as verify:
        assert count(verify, SpecimenEvent) == 0
        assert count(verify, SpecimenState) == 0
        assert count(verify, WorkflowOutbox) == 0


def test_invalid_timestamp_or_uuid_is_rejected_without_writes(sessions):
    payload = sample_event()
    with sessions() as db:
        with pytest.raises(ValidationError):
            process_stream_event(dict(payload, occurred_at="2026-10-30T12:00:00"), db)
        with pytest.raises(ValidationError):
            process_stream_event(dict(payload, event_id="not-a-uuid"), db)
        assert count(db, SpecimenEvent) == 0


def test_concurrent_events_always_preserve_latest_state(sessions):
    now = datetime(2026, 10, 30, 15, tzinfo=timezone.utc)
    earlier = sample_event(status="PROCESSING", occurred_at=now - timedelta(hours=2))
    later = sample_event(status="SIGNED_OUT", occurred_at=now)

    def submit(item):
        with sessions() as db:
            return process_stream_event(item, db)

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(submit, [later, earlier]))

    with sessions() as verify:
        state = verify.get(SpecimenState, "SPECIMEN_synthetic")
        assert state.current_status == "SIGNED_OUT"
        assert state.last_event_at == now
        assert count(verify, SpecimenEvent) == 2
        assert count(verify, WorkflowOutbox) == 2
