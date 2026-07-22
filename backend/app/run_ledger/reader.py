from __future__ import annotations

from sqlalchemy.orm import Session

from app.contracts.ledger_events import LedgerEvent
from app.models.db import RunLedgerEventRecord
from app.run_ledger.persistence import record_to_event


class RunLedgerReader:
    def __init__(self, db: Session):
        self.db = db

    def list_events(self, run_id: str) -> list[LedgerEvent]:
        records = (
            self.db.query(RunLedgerEventRecord)
            .filter(RunLedgerEventRecord.run_id == run_id)
            .order_by(RunLedgerEventRecord.step_index, RunLedgerEventRecord.created_at)
            .all()
        )
        return [record_to_event(record) for record in records]

    def get_event(self, event_id: str) -> LedgerEvent | None:
        record = self.db.get(RunLedgerEventRecord, event_id)
        return record_to_event(record) if record else None
