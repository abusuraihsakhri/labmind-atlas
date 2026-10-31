"""Transactional specimen event ingestion.

A Redis event becomes safe to acknowledge only after its source record, ordered
state projection and one durable workflow-outbox item commit together.

The outbox deliberately has no dispatcher in P1; a retry-safe dispatcher and
pending-entry recovery are separate follow-on work (issue #3).
"""
from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from agents.models import SpecimenEvent, SpecimenState, WorkflowOutbox


TAT_MAP = {
    "HISTO-01": 2880,
    "CHEM-20": 60,
    "HEMA-10": 45,
}


class IngestEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: UUID
    specimen_token: str = Field(min_length=1, max_length=255)
    event_type: str = Field(min_length=1, max_length=100)
    test_code: str = Field(min_length=1, max_length=100)
    status: str = Field(min_length=1, max_length=100)
    occurred_at: AwareDatetime
    received_at: AwareDatetime
    clinician_token: str = Field(min_length=1, max_length=255)
    de_identified_comments: str


@dataclass(frozen=True)
class IngestOutcome:
    event_id: UUID
    duplicate: bool
    state_applied: bool


class ConflictingEventId(ValueError):
    """A previously committed event ID is reused with different source data."""


def _same_source_event(existing: SpecimenEvent, incoming: IngestEvent) -> bool:
    # received_at is assigned by the gateway and may change if the same LIS
    # event is resubmitted. Compare stable, source-derived fields instead.
    return (
        existing.specimen_token == incoming.specimen_token
        and existing.event_type == incoming.event_type
        and existing.test_code == incoming.test_code
        and existing.status == incoming.status
        and existing.occurred_at == incoming.occurred_at
        and existing.anon_clinician_token == incoming.clinician_token
        and (existing.meta_jsonb or {}).get("comments") == incoming.de_identified_comments
    )


def process_stream_event(event_data: dict, db: Session) -> IngestOutcome:
    """Persist one event with idempotency and ordered projection.

    PostgreSQL upserts serialize concurrent writes using the primary keys.
    Equal or older timestamps remain in history but cannot change live status.
    No workflow or notification executes in this transaction.
    Exceptions propagate to the listener; the caller must not XACK them.
    """
    try:
        event = IngestEvent.model_validate(event_data)

        inserted_id = db.execute(
            pg_insert(SpecimenEvent)
            .values(
                id=event.event_id,
                specimen_token=event.specimen_token,
                event_type=event.event_type,
                test_code=event.test_code,
                status=event.status,
                occurred_at=event.occurred_at,
                received_at=event.received_at,
                anon_clinician_token=event.clinician_token,
                meta_jsonb={"comments": event.de_identified_comments},
            )
            .on_conflict_do_nothing(index_elements=[SpecimenEvent.id])
            .returning(SpecimenEvent.id)
        ).scalar_one_or_none()

        if inserted_id is None:
            existing = db.get(SpecimenEvent, event.event_id)
            if existing is None or not _same_source_event(existing, event):
                raise ConflictingEventId(
                    f"Event ID {event.event_id} was reused with conflicting source data"
                )
            db.commit()
            return IngestOutcome(event.event_id, duplicate=True, state_applied=False)

        # The conditional conflict update is atomic under concurrent consumers.
        # Do not let an older or equal-timestamp event overwrite current state.
        state_id = db.execute(
            pg_insert(SpecimenState)
            .values(
                specimen_token=event.specimen_token,
                current_status=event.status,
                accessioned_at=event.occurred_at,
                expected_signout_at=event.occurred_at
                + timedelta(minutes=TAT_MAP.get(event.test_code, 60)),
                tat_risk_level="green",
                last_event_at=event.occurred_at,
            )
            .on_conflict_do_update(
                index_elements=[SpecimenState.specimen_token],
                set_={
                    "current_status": event.status,
                    "last_event_at": event.occurred_at,
                },
                where=SpecimenState.last_event_at < event.occurred_at,
            )
            .returning(SpecimenState.specimen_token)
        ).scalar_one_or_none()
        state_applied = state_id is not None

        db.add(
            WorkflowOutbox(
                event_id=event.event_id,
                specimen_token=event.specimen_token,
                clinician_token=event.clinician_token,
                state_applied=state_applied,
                status="pending",
            )
        )
        db.commit()
        return IngestOutcome(event.event_id, duplicate=False, state_applied=state_applied)
    except Exception:
        db.rollback()
        raise
