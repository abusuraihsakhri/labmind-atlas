"""Redis XACK safety boundary tests without external services."""
import json
from contextlib import nullcontext
from unittest.mock import Mock

from agents import pipeline
from agents.ingestion import IngestOutcome

MESSAGE_ID = b"1-0"
STREAM = "specimen_events_stream"
GROUP = "agents_group"


def test_ack_only_after_committed_ingestion(monkeypatch):
    client = Mock()
    observed = []
    raw = json.dumps({"event_id": "00000000-0000-4000-8000-000000000001", "event_type": "ORDER_PLACED", "status": "ORDERED"}).encode()
    monkeypatch.setattr(pipeline, "stream_retry_state", lambda _id: "ready")
    monkeypatch.setattr(pipeline, "record_stream_success", lambda _id: observed.append("recorded"))
    monkeypatch.setattr(pipeline, "SessionLocal", lambda: nullcontext(Mock()))

    def committed(_event, _db):
        observed.append("committed")
        return IngestOutcome("00000000-0000-4000-8000-000000000001", False, True)

    monkeypatch.setattr(pipeline, "process_stream_event", committed)
    client.xack.side_effect = lambda *_args: observed.append("acked")
    assert pipeline.handle_stream_message(client, STREAM, GROUP, MESSAGE_ID, {b"event": raw})
    assert observed == ["committed", "recorded", "acked"]
    client.xack.assert_called_once_with(STREAM, GROUP, MESSAGE_ID)


def test_failure_stays_pending(monkeypatch):
    client = Mock()
    monkeypatch.setattr(pipeline, "stream_retry_state", lambda _id: "ready")
    monkeypatch.setattr(pipeline, "SessionLocal", lambda: nullcontext(Mock()))
    monkeypatch.setattr(pipeline, "process_stream_event", lambda *_args: (_ for _ in ()).throw(RuntimeError()))
    failures = []
    monkeypatch.setattr(
        pipeline, "record_stream_failure",
        lambda sid, hashed, exc: failures.append((sid, hashed, type(exc).__name__)) or "pending",
    )
    assert not pipeline.handle_stream_message(
        client, STREAM, GROUP, MESSAGE_ID, {b"event": b'{"event_id":"x"}'}
    )
    client.xack.assert_not_called()
    assert failures[0][0] == "specimen_events_stream:1-0"
    assert failures[0][2] == "RuntimeError"


def test_dead_letter_acked_only_after_durable_record(monkeypatch):
    client = Mock()
    monkeypatch.setattr(pipeline, "stream_retry_state", lambda _id: "ready")
    monkeypatch.setattr(
        pipeline, "record_stream_failure",
        lambda _sid, _hash, _exc: "dead_letter",
    )
    assert not pipeline.handle_stream_message(client, STREAM, GROUP, MESSAGE_ID, {})
    client.xack.assert_called_once_with(STREAM, GROUP, MESSAGE_ID)


def test_failed_dead_letter_persistence_never_acks(monkeypatch):
    client = Mock()
    monkeypatch.setattr(pipeline, "stream_retry_state", lambda _id: "ready")

    def failure(*_args):
        raise RuntimeError("database down")

    monkeypatch.setattr(pipeline, "record_stream_failure", failure)
    import pytest
    with pytest.raises(RuntimeError, match="database down"):
        pipeline.handle_stream_message(client, STREAM, GROUP, MESSAGE_ID, {})
    client.xack.assert_not_called()


def test_deferred_pending_entries_not_acked(monkeypatch):
    client = Mock()
    monkeypatch.setattr(pipeline, "stream_retry_state", lambda _id: "defer")
    assert not pipeline.handle_stream_message(client, STREAM, GROUP, MESSAGE_ID, {})
    client.xack.assert_not_called()


def test_retry_ledger_key_distinguishes_streams(monkeypatch):
    client = Mock()
    keys = []
    def retry_lookup(key):
        keys.append(key)
        return "defer"
    monkeypatch.setattr(pipeline, "stream_retry_state", retry_lookup)
    assert not pipeline.handle_stream_message(client, "stream_one", GROUP, MESSAGE_ID, {})
    assert not pipeline.handle_stream_message(client, "stream_two", GROUP, MESSAGE_ID, {})
    assert keys == ["stream_one:1-0", "stream_two:1-0"]
    client.xack.assert_not_called()
