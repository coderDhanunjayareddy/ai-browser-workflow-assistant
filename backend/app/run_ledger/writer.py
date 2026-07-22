from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.contracts.ledger_events import LedgerEvent
from app.feature_flags import is_shadow_or_active
from app.run_ledger.persistence import event_to_record

logger = logging.getLogger(__name__)


class RunLedgerWriter:
    """Append-only V3 run ledger writer.

    Shadow writes are diagnostics only. Write failures are swallowed by default
    so the foundation cannot change production workflow behavior.
    """

    def __init__(self, db: Session | None = None, *, strict: bool = False):
        self.db = db
        self.strict = strict

    def append(
        self,
        *,
        run_id: str,
        event_type: str,
        payload: dict[str, Any] | None = None,
        step_index: int = 0,
        producer: str = "backend.workflow_orchestrator",
        links: dict[str, Any] | None = None,
    ) -> LedgerEvent | None:
        if not is_shadow_or_active("V3_RUN_LEDGER"):
            return None
        event = LedgerEvent(
            run_id=run_id,
            event_type=event_type,
            payload=payload or {},
            step_index=step_index,
            producer=producer,
            links=links or {},
        )
        if self.db is None:
            return event
        try:
            self.db.add(event_to_record(event))
            self.db.commit()
        except Exception:
            self.db.rollback()
            logger.exception("V3 run ledger append failed for run %s", run_id)
            if self.strict:
                raise
            return None
        return event
