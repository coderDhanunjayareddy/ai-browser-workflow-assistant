from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from app.core.database import SessionLocal
from app.contracts.ledger_events import LedgerEvent
from app.feature_flags import is_shadow_or_active
from app.run_ledger.persistence import event_to_record

logger = logging.getLogger(__name__)

_session_factory = None


def _set_session_factory(factory) -> None:
    global _session_factory
    _session_factory = factory


def _reset_session_factory() -> None:
    global _session_factory
    _session_factory = None


@contextmanager
def _isolated_session_scope(factory_override=None):
    factory = factory_override or _session_factory or SessionLocal
    db = factory()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class RunLedgerWriter:
    """Append-only V3 run ledger writer.

    Shadow writes are diagnostics only. Write failures are swallowed by default
    so the foundation cannot change production workflow behavior.
    """

    def __init__(self, db: Session | None = None, *, strict: bool = False):
        # db is retained only for strict tests. Otherwise its engine bind is
        # used to create a separate session and transaction for ledger writes.
        self.db = db
        self.strict = strict
        self._session_factory = None
        if db is not None and not strict:
            self._session_factory = sessionmaker(
                bind=db.get_bind(),
                autocommit=False,
                autoflush=False,
            )

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
        if self.db is None and self.strict:
            return event
        try:
            if self.db is not None and self.strict:
                self.db.add(event_to_record(event))
                self.db.commit()
            else:
                with _isolated_session_scope(self._session_factory) as db:
                    db.add(event_to_record(event))
        except Exception:
            if self.db is not None and self.strict:
                self.db.rollback()
            logger.exception("V3 run ledger append failed for run %s", run_id)
            if self.strict:
                raise
            return None
        return event
