from __future__ import annotations

from app.contracts.ledger_events import LedgerEvent
from app.models.db import RunLedgerEventRecord
from app.run_ledger.privacy import sanitize_ledger_payload


def event_to_record(event: LedgerEvent) -> RunLedgerEventRecord:
    return RunLedgerEventRecord(
        event_id=event.event_id,
        run_id=event.run_id,
        step_index=event.step_index,
        event_type=event.event_type,
        schema_version=event.schema_version,
        producer=event.producer,
        payload=sanitize_ledger_payload(event.payload),
        links=sanitize_ledger_payload(event.links),
        created_at=event.created_at.replace(tzinfo=None),
    )


def record_to_event(record: RunLedgerEventRecord) -> LedgerEvent:
    return LedgerEvent(
        schema_version=record.schema_version,
        producer=record.producer,
        created_at=record.created_at,
        run_id=record.run_id,
        event_id=record.event_id,
        step_index=record.step_index,
        event_type=record.event_type,
        payload=record.payload or {},
        links=record.links or {},
    )
