"""Redis stream ingestion with crash recovery and durable dead-letter handling."""
import hashlib
import json
import logging
import os
import signal
import socket
import threading
import time
from uuid import uuid4

import redis

from agents.database import SessionLocal
from agents.ingestion import process_stream_event
from agents.metrics import (
    events_processed_total,
    pipeline_batch_size,
    pipeline_processing_seconds,
)
from agents.retry import (
    record_stream_failure,
    record_stream_success,
    stream_retry_state,
)

logger = logging.getLogger("labmind.pipeline")
BATCH_SIZE = max(1, int(os.getenv("PIPELINE_BATCH_SIZE", "10")))
CLAIM_IDLE_MS = max(1000, int(os.getenv("PIPELINE_CLAIM_IDLE_MS", "30000")))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_shutdown_requested = False


def _handle_shutdown(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("Shutdown signal %s; all unprocessed messages remain pending", signum)


def handle_stream_message(client, stream_name, group, message_id, payload):
    """XACK only after a successful ingestion commit or durable dead letter."""
    stream_id = message_id.decode() if isinstance(message_id, bytes) else str(message_id)
    state = stream_retry_state(stream_id)
    if state == "defer":
        return False
    if state == "dead_letter":
        client.xack(stream_name, group, message_id)
        return True

    raw = payload.get(b"event")
    payload_hash = hashlib.sha256(raw if isinstance(raw, bytes) else b"missing").hexdigest()
    started_at = time.monotonic()
    try:
        if not isinstance(raw, bytes):
            raise ValueError("Missing event field")
        event = json.loads(raw)
        if not isinstance(event, dict):
            raise ValueError("Event must be a JSON object")
        with SessionLocal() as db:
            outcome = process_stream_event(event, db)
    except Exception as exc:
        # Never log untrusted payload, value text or exception strings (may
        # include patient content); error type and payload hash suffice.
        logger.warning("Stream event %s processing failed (%s)", stream_id, type(exc).__name__)
        status = record_stream_failure(stream_id, payload_hash, exc)
        if status == "dead_letter":
            # Dead-letter metadata must be committed before acknowledgement.
            client.xack(stream_name, group, message_id)
            logger.error("Stream entry %s quarantined after bounded failures", stream_id)
        return False
    finally:
        pipeline_processing_seconds.observe(time.monotonic() - started_at)

    # A failed diagnostic update or Redis XACK leaves the source recoverable.
    record_stream_success(stream_id)
    client.xack(stream_name, group, message_id)
    if not outcome.duplicate:
        events_processed_total.labels(
            event_type=event["event_type"], status=event["status"]
        ).inc()
    return True


def start_pipeline_listener(stop_event=None):
    global _shutdown_requested
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _handle_shutdown)
        signal.signal(signal.SIGTERM, _handle_shutdown)

    client = redis.Redis.from_url(REDIS_URL)
    stream = "specimen_events_stream"
    group = "agents_group"
    consumer = f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:8]}"
    try:
        client.xgroup_create(stream, group, id="0", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise

    def stopped():
        return _shutdown_requested or (stop_event is not None and stop_event.is_set())

    logger.info("Redis stream consumer started: %s", consumer)
    while not stopped():
        try:
            # Reclaim abandoned entries before consuming new ones. Reclaimed
            # events remain subject to the persisted next-retry timestamp.
            _cursor, claimed, _deleted = client.xautoclaim(
                stream, group, consumer,
                min_idle_time=CLAIM_IDLE_MS,
                start_id="0-0",
                count=BATCH_SIZE,
            )
            batches = [(stream, claimed)] if claimed else client.xreadgroup(
                group, consumer, {stream: ">"}, count=BATCH_SIZE, block=2000
            )
            for _stream, entries in batches:
                handled = 0
                for message_id, payload in entries:
                    if stopped():
                        break
                    try:
                        if handle_stream_message(client, stream, group, message_id, payload):
                            handled += 1
                    except Exception:
                        # In particular, never acknowledge when retry/dead-letter
                        # metadata cannot be committed.
                        logger.exception("Stream processing infrastructure failed")
                        time.sleep(2)
                pipeline_batch_size.observe(handled)
                if stopped():
                    break
        except Exception:
            if stopped():
                break
            logger.exception("Redis stream listener error")
            time.sleep(2)
    logger.info("Redis stream listener stopped; unprocessed entries are pending")


if __name__ == "__main__":
    start_pipeline_listener()
