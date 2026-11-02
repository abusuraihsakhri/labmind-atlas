"""PostgreSQL + Redis integration tests for P2 crash/replay and dead letters."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import redis
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import sessionmaker

from agents import outbox, pipeline
from agents.ingestion import process_stream_event
from agents.models import Action, AuditEvent, SpecimenEvent, StreamFailure, WorkflowOutbox
from agents.retry import MAX_ATTEMPTS

PG_URL = os.getenv("LABMIND_TEST_DATABASE_URL")
REDIS_URL = os.getenv("LABMIND_TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(
    not PG_URL or not REDIS_URL,
    reason="Requires isolated PostgreSQL and Redis test services",
)


@pytest.fixture
def services(monkeypatch):
    engine = create_engine(PG_URL, pool_pre_ping=True)
    sessions = sessionmaker(bind=engine, autoflush=False)
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE workflow_outbox, stream_failures, specimen_state, "
            "specimen_events, actions, audit_events CASCADE"
        ))
    monkeypatch.setattr(outbox, "SessionLocal", sessions)
    monkeypatch.setattr(pipeline, "SessionLocal", sessions)
    import agents.retry as retries
    monkeypatch.setattr(retries, "SessionLocal", sessions)
    client = redis.Redis.from_url(REDIS_URL)
    yield sessions, client
    engine.dispose()


def event_payload(status="PROCESSING", comments="Synthetic normal"):
    timestamp = datetime.now(timezone.utc) - timedelta(hours=4)
    return {
        "event_id": str(uuid4()),
        "specimen_token": "SPECIMEN_p2_synthetic",
        "event_type": "PROCESSING_STARTED",
        "test_code": "CHEM-20",
        "status": status,
        "occurred_at": timestamp.isoformat(),
        "received_at": (timestamp + timedelta(minutes=1)).isoformat(),
        "clinician_token": "CLINICIAN_synthetic",
        "de_identified_comments": comments,
    }


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_outbox_processing_is_deterministic_and_side_effect_free(services):
    sessions, _client = services
    payload = event_payload(comments="CRITICAL VALUE: synthetic only")
    with sessions() as db:
        process_stream_event(payload, db)
    assert outbox.run_outbox_batch(session_factory=sessions, trust_stage="SUGGEST") == 1
    assert outbox.run_outbox_batch(session_factory=sessions, trust_stage="SUGGEST") == 0
    with sessions() as db:
        row = db.get(WorkflowOutbox, payload["event_id"])
        assert row.status == "completed"
        assert count(db, Action) == 2
        assert count(db, AuditEvent) == 2
        critical = db.scalar(select(Action).where(
            Action.action_type == "REVIEW_UNVERIFIED_CRITICAL_SIGNAL"
        ))
        assert critical.payload_jsonb["dispatch_allowed"] is False
        assert critical.status == "proposed"


def test_crash_before_commit_does_not_duplicate_proposals(services, monkeypatch):
    sessions, _client = services
    payload = event_payload()
    with sessions() as db:
        process_stream_event(payload, db)
    real_audit = outbox.ActionExecutor.log_audit_event
    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("injected audit rollback")
    monkeypatch.setattr(outbox.ActionExecutor, "log_audit_event", fail_audit)
    assert outbox.run_outbox_batch(session_factory=sessions, trust_stage="SUGGEST") == 0
    with sessions() as db:
        row = db.get(WorkflowOutbox, payload["event_id"])
        assert row.status == "pending"
        assert row.attempts == 1
        assert count(db, Action) == 0
        row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    monkeypatch.setattr(outbox.ActionExecutor, "log_audit_event", real_audit)
    assert outbox.run_outbox_batch(session_factory=sessions, trust_stage="SUGGEST") == 1
    with sessions() as db:
        assert count(db, Action) == 1
        assert count(db, AuditEvent) == 1


def test_concurrent_outbox_consumers_create_one_proposal(services):
    sessions, _client = services
    payload = event_payload()
    with sessions() as db:
        process_stream_event(payload, db)
    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(
            lambda _: outbox.run_outbox_batch(session_factory=sessions, trust_stage="SUGGEST"),
            range(2),
        ))
    with sessions() as db:
        assert count(db, Action) == 1
        assert db.get(WorkflowOutbox, payload["event_id"]).status == "completed"


def test_outbox_dead_letters_after_bounded_failures(services, monkeypatch):
    sessions, _client = services
    payload = event_payload()
    with sessions() as db:
        process_stream_event(payload, db)
    monkeypatch.setattr(
        outbox, "process_outbox_event",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("bad workflow")),
    )
    for retry in range(MAX_ATTEMPTS):
        assert outbox.run_outbox_batch(session_factory=sessions) == 0
        with sessions() as db:
            row = db.get(WorkflowOutbox, payload["event_id"])
            assert row.attempts == retry + 1
            if retry < MAX_ATTEMPTS - 1:
                row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                db.commit()
    with sessions() as db:
        assert db.get(WorkflowOutbox, payload["event_id"]).status == "dead_letter"
        assert count(db, Action) == 0


def new_stream(client, payload):
    name = "labmind_p2_test_" + uuid4().hex
    client.xgroup_create(name, "testgroup", id="0", mkstream=True)
    mid = client.xadd(name, {b"event": payload})
    read = client.xreadgroup("testgroup", "crashed_worker", {name: ">"}, count=1)
    return name, mid, read[0][1][0][1]


def test_restart_reclaims_pending_entry_and_commits_before_ack(services):
    sessions, client = services
    payload = event_payload()
    name, mid, raw = new_stream(client, json.dumps(payload).encode())
    try:
        time.sleep(0.03)
        _cursor, reclaimed, _deleted = client.xautoclaim(
            name, "testgroup", "replacement_worker",
            min_idle_time=1, start_id="0-0", count=10,
        )
        assert reclaimed[0][0] == mid
        assert pipeline.handle_stream_message(client, name, "testgroup", mid, raw)
        assert client.xpending(name, "testgroup")["pending"] == 0
        with sessions() as db:
            assert count(db, SpecimenEvent) == 1
            assert count(db, WorkflowOutbox) == 1
    finally:
        client.delete(name)


def test_malformed_event_retries_then_durable_quarantine(services):
    sessions, client = services
    name, mid, raw = new_stream(client, b"{invalid json")
    try:
        for attempt in range(MAX_ATTEMPTS):
            assert not pipeline.handle_stream_message(
                client, name, "testgroup", mid, raw
            )
            with sessions() as db:
                item = db.get(StreamFailure, mid.decode())
                assert item.attempts == attempt + 1
                if attempt < MAX_ATTEMPTS - 1:
                    assert client.xpending(name, "testgroup")["pending"] == 1
                    item.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
                    db.commit()
        assert client.xpending(name, "testgroup")["pending"] == 0
        with sessions() as db:
            item = db.get(StreamFailure, mid.decode())
            assert item.status == "dead_letter"
            assert item.error_code == "JSONDecodeError"
            assert item.payload_sha256 is not None
    finally:
        client.delete(name)
