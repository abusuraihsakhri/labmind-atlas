import os
import json
import time
import signal
import logging
import redis
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session
from agents.database import SessionLocal
from agents.models import SpecimenEvent, SpecimenState
from agents.metrics import events_processed_total, pipeline_batch_size, pipeline_processing_seconds

logger = logging.getLogger("labmind.pipeline")

BATCH_SIZE = int(os.getenv("PIPELINE_BATCH_SIZE", "10"))
_shutdown_requested = False


def _handle_shutdown(signum, frame):
    global _shutdown_requested
    _shutdown_requested = True
    logger.info("Shutdown signal received (signal=%d). Draining pipeline...", signum)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Setup nominal TAT mapper for state initializer
TAT_MAP = {
    "HISTO-01": 2880, # 48 hours
    "CHEM-20": 60,    # 1 hour
    "HEMA-10": 45,    # 45 mins
}

def process_stream_event(event_data: dict, db: Session):
    try:
        import time as _time
        start = _time.monotonic()

        occurred_at = datetime.fromisoformat(event_data["occurred_at"])
        received_at = datetime.fromisoformat(event_data["received_at"])
        
        event_entry = SpecimenEvent(
            id=event_data["event_id"],
            specimen_token=event_data["specimen_token"],
            event_type=event_data["event_type"],
            test_code=event_data["test_code"],
            status=event_data["status"],
            occurred_at=occurred_at,
            received_at=received_at,
            anon_clinician_token=event_data["clinician_token"],
            meta_jsonb={"comments": event_data["de_identified_comments"]}
        )
        db.add(event_entry)
        
        # Update or Create SpecimenState (Working memory mirror)
        state = db.query(SpecimenState).filter(SpecimenState.specimen_token == event_data["specimen_token"]).first()
        
        if not state:
            # First time seeing this specimen (accessioning)
            nominal_minutes = TAT_MAP.get(event_data["test_code"], 60)
            expected_signout = occurred_at + timedelta(minutes=nominal_minutes)
            
            state = SpecimenState(
                specimen_token=event_data["specimen_token"],
                current_status=event_data["status"],
                accessioned_at=occurred_at,
                expected_signout_at=expected_signout,
                tat_risk_level="green",
                last_event_at=occurred_at
            )
            db.add(state)
        else:
            # Update status and timestamps
            state.current_status = event_data["status"]
            state.last_event_at = occurred_at
            
        db.commit()
        elapsed = _time.monotonic() - start
        pipeline_processing_seconds.observe(elapsed)
        events_processed_total.labels(
            event_type=event_data["event_type"],
            status=event_data["status"]
        ).inc()
        logger.info("Processed event %s for specimen %s (%.3fs)", event_data['event_type'], event_data['specimen_token'], elapsed)
        
        # Trigger Workflow Manager evaluation
        from agents.workflow_manager import WorkflowManagerAgent
        from agents.main import GLOBAL_CONFIG
        
        manager = WorkflowManagerAgent()
        manager.process_specimen_update(
            specimen_token=event_data["specimen_token"],
            db=db,
            clinician_token=event_data["clinician_token"],
            trust_stage=GLOBAL_CONFIG.get("trust_stage", "SUGGEST")
        )
        
    except Exception as e:

        db.rollback()
        logger.error("Failed to process event: %s", e, exc_info=True)

def start_pipeline_listener():
    global _shutdown_requested

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)

    r = redis.Redis.from_url(REDIS_URL)
    stream_name = "specimen_events_stream"
    
    logger.info("Pipeline listener starting. Monitoring Redis stream: %s", stream_name)
    
    # Create the stream if it does not exist
    try:
        r.xgroup_create(stream_name, "agents_group", id="0", mkstream=True)
    except redis.exceptions.ResponseError:
        pass

    while not _shutdown_requested:
        try:
            messages = r.xreadgroup("agents_group", "consumer_1", {stream_name: ">"}, count=BATCH_SIZE, block=2000)
            if not messages:
                continue
                
            for stream, stream_msgs in messages:
                batch = []
                for msg_id, payload in stream_msgs:
                    if _shutdown_requested:
                        logger.info("Shutdown requested. Acknowledging remaining messages and exiting.")
                        r.xack(stream_name, "agents_group", msg_id)
                        continue

                    event_json = payload[b"event"].decode("utf-8")
                    event_data = json.loads(event_json)
                    batch.append((msg_id, event_data))

                if not batch:
                    break

                db = SessionLocal()
                try:
                    for msg_id, event_data in batch:
                        process_stream_event(event_data, db)
                        r.xack(stream_name, "agents_group", msg_id)
                    pipeline_batch_size.observe(len(batch))
                    logger.info("Processed batch of %d events", len(batch))
                except Exception as e:
                    logger.error("Batch processing error (messages will be retried): %s", e, exc_info=True)
                finally:
                    db.close()
        except Exception as e:
            if _shutdown_requested:
                break
            logger.error("Pipeline loop error: %s", e, exc_info=True)
            time.sleep(2)

    logger.info("Pipeline listener stopped gracefully.")

if __name__ == "__main__":
    start_pipeline_listener()
