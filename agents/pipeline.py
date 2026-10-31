"""Redis Stream consumer for durable, transactional specimen ingestion.

P1 safeguards the commit/XACK boundary. Pending-entry reclamation, bounded
retry and dead-letter routing remain required in the next change (issue #3).
"""
import json
import logging
import os
import signal
import threading
import time

import redis

from agents.database import SessionLocal
from agents.ingestion import process_stream_event
from agents.metrics import (
    events_processed_total,
    pipeline_batch_size,
    pipeline_processing_seconds,
)

logger = logging.getLogger("labmind.pipeline")

BATCH_SIZE = int(os.getenv("PIPELINE_BATCH_SIZE", "10"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_shutdown_requested = False


def _handle_shutdown(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("Shutdown signal received (%s); leaving unprocessed stream entries pending", signum)


def start_pipeline_listener():
    global _shutdown_requested
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, _handle_shutdown)
        signal.signal(signal.SIGTERM, _handle_shutdown)

    client = redis.Redis.from_url(REDIS_URL)
    stream_name = "specimen_events_stream"
    group = "agents_group"

    try:
        client.xgroup_create(stream_name, group, id="0", mkstream=True)
    except redis.exceptions.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise

    logger.info("Starting specimen event ingestion from %s", stream_name)

    while not _shutdown_requested:
        try:
            # P1 handles new entries only. P2 will reclaim the pending list.
            messages = client.xreadgroup(
                group, "consumer_1", {stream_name: ">"}, count=BATCH_SIZE, block=2000
            )
            for _stream, entries in messages:
                handled = 0
                for message_id, payload in entries:
                    if _shutdown_requested:
                        # Never XACK entries which have not committed successfully.
                        break

                    started_at = time.monotonic()
                    db = SessionLocal()
                    try:
                        raw_event = payload[b"event"]
                        event_data = json.loads(raw_event)
                        outcome = process_stream_event(event_data, db)

                        # PostgreSQL has committed the event + state + outbox.
                        # ACK failures are safe to replay (event ID is unique).
                        client.xack(stream_name, group, message_id)

                        if not outcome.duplicate:
                            events_processed_total.labels(
                                event_type=event_data["event_type"],
                                status=event_data["status"],
                            ).inc()
                        handled += 1
                    except Exception:
                        db.rollback()
                        logger.exception(
                            "Stream entry %s NOT acknowledged; recovery required",
                            message_id,
                        )
                    finally:
                        db.close()
                        pipeline_processing_seconds.observe(time.monotonic() - started_at)

                pipeline_batch_size.observe(handled)
                if _shutdown_requested:
                    break
        except Exception:
            if _shutdown_requested:
                break
            logger.exception("Stream listener failure")
            time.sleep(2)

    logger.info("Specimen event listener stopped with unprocessed entries pending")


if __name__ == "__main__":
    start_pipeline_listener()
