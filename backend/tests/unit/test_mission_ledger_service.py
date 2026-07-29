from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.intent_dispatcher import dispatch_intent, execute_intent_queue
from app.intent_dispatcher.models import ExecutionContext
from app.models import db as _models  # noqa: F401
from app.schemas.intent import IntentEvidence
from app.services import mission_ledger_service


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)()


def test_browser_handoff_persists_intent_and_returns_next_ledger_intent():
    db = _session()
    try:
        mission_id = "mission-ledger-test"
        directive = dispatch_intent(
            intent="navigate",
            payload={
                "action_type": "navigate",
                "value": "https://example.test",
                "next_intents": [
                    {
                        "intent": "validate_records",
                        "payload": {"record_ids": ["record_1"]},
                    }
                ],
            },
        )
        assert directive is not None

        queue_result = execute_intent_queue(
            mission_id=mission_id,
            initial_intents=[directive],
            context=ExecutionContext(mission_id=mission_id, task="Open and validate."),
        )
        mission_ledger_service.record_queue_result(
            db,
            mission_id=mission_id,
            initial_intent=directive,
            queue_result=queue_result,
        )

        assigned = mission_ledger_service.next_intent(db, mission_id=mission_id, provider="browser_control")
        assert assigned.intent is not None
        assert assigned.intent.intent_id == directive.intent_id
        assert assigned.intent.status == "EXECUTING"

        updated = mission_ledger_service.update_intent(
            db,
            mission_id=mission_id,
            intent_id=directive.intent_id,
            outcome="success",
            evidence=IntentEvidence(
                evidence_type="browser_execution",
                success=True,
                message="Opened https://example.test",
                payload={"intent_id": directive.intent_id},
                browser_metadata={"tab_url": "https://example.test"},
                provider_metadata={"provider": "browser_control"},
            ),
        )

        assert updated.status == "COMPLETED"
        assert updated.next_intent is not None
        assert updated.next_intent.parent_intent_id == directive.intent_id
        assert updated.next_intent.intent == "validate_records"
    finally:
        db.close()
