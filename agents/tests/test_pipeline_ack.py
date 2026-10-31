"""Redis XACK boundary tests for P1 (P2 will add pending recovery)."""
import json
from unittest.mock import Mock

from agents import pipeline
from agents.ingestion import IngestOutcome


class OneMessageRedis:
    def __init__(self):
        self.acks = []
        self.reads = 0

    def xgroup_create(self, *_args, **_kwargs):
        return True

    def xreadgroup(self, *_args, **_kwargs):
        self.reads += 1
        if self.reads == 1:
            message = json.dumps({"event_id": "00000000-0000-4000-8000-000000000001"})
            return [(b"specimen_events_stream", [(b"1-0", {b"event": message.encode()})])]
        pipeline._shutdown_requested = True
        return []

    def xack(self, *args):
        self.acks.append(args)


def exercise_listener(monkeypatch, ingest):
    client = OneMessageRedis()
    session = Mock()
    monkeypatch.setattr(pipeline.redis.Redis, "from_url", lambda _url: client)
    monkeypatch.setattr(pipeline, "SessionLocal", lambda: session)
    monkeypatch.setattr(pipeline, "process_stream_event", ingest)
    monkeypatch.setattr(pipeline.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(pipeline, "_shutdown_requested", False)
    try:
        pipeline.start_pipeline_listener()
    finally:
        pipeline._shutdown_requested = False
    return client, session


def test_ack_occurs_only_after_successful_commit(monkeypatch):
    completed = []

    def committed(_payload, _db):
        completed.append(True)
        return IngestOutcome(
            event_id="00000000-0000-4000-8000-000000000001",
            duplicate=True,
            state_applied=False,
        )

    client, _session = exercise_listener(monkeypatch, committed)
    assert completed
    assert client.acks == [("specimen_events_stream", "agents_group", b"1-0")]


def test_failing_ingest_is_not_acknowledged(monkeypatch):
    def failed(_payload, _db):
        raise RuntimeError("injected PostgreSQL failure")

    client, session = exercise_listener(monkeypatch, failed)
    assert client.acks == []
    session.rollback.assert_called()


def test_shutdown_does_not_ack_unprocessed_entries(monkeypatch):
    client = OneMessageRedis()
    monkeypatch.setattr(pipeline.redis.Redis, "from_url", lambda _url: client)
    monkeypatch.setattr(pipeline.signal, "signal", lambda *_args: None)
    monkeypatch.setattr(pipeline, "_shutdown_requested", True)
    pipeline.start_pipeline_listener()
    assert client.acks == []
    pipeline._shutdown_requested = False
