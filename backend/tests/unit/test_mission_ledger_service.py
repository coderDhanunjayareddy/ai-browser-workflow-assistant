from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.intent_dispatcher import dispatch_intent, execute_intent_queue
from app.intent_dispatcher.models import ExecutionContext
from app.models.db import MissionIntentRecord
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
                        "intent": "open_new_tab",
                        "payload": {"value": "https://second.example"},
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

        assert updated.status == "ready"
        assert updated.next_intent is not None
        assert updated.next_intent.parent_intent_id == directive.intent_id
        assert updated.next_intent.intent == "open_new_tab"
    finally:
        db.close()


def test_next_intent_skips_surplus_open_tabs_after_blueprint_source_cap():
    db = _session()
    try:
        mission_id = "mission-ledger-source-cap"
        mission_ledger_service.ensure_session(db, mission_id)
        base_time = datetime.utcnow()

        for index in range(1, 6):
            db.add(
                MissionIntentRecord(
                    intent_id=f"open-result-{index}",
                    mission_id=mission_id,
                    intent="open_new_tab",
                    provider="browser_control",
                    capability="tabs.open",
                    dispatch_target="extension",
                    execution_owner="browser_control",
                    status="COMPLETED",
                    payload={"value": f"https://source{index}.example.test"},
                    evidence=[],
                    provenance={},
                    resume_metadata={},
                    blueprint_id="bp-source-cap",
                    blueprint_node_id=f"open_result_{index}",
                    blueprint_revision=1,
                    created_at=base_time + timedelta(seconds=index),
                    updated_at=base_time + timedelta(seconds=index),
                    completed_at=base_time + timedelta(seconds=index),
                )
            )

        db.add(
            MissionIntentRecord(
                intent_id="surplus-open",
                mission_id=mission_id,
                intent="open_new_tab",
                provider="browser_control",
                capability="tabs.open",
                dispatch_target="extension",
                execution_owner="browser_control",
                status="QUEUED",
                payload={"value": "https://extra.example.test"},
                evidence=[],
                provenance={},
                resume_metadata={},
                created_at=base_time + timedelta(seconds=10),
                updated_at=base_time + timedelta(seconds=10),
            )
        )
        db.add(
            MissionIntentRecord(
                intent_id="focus-source",
                mission_id=mission_id,
                intent="focus_existing_tab",
                provider="browser_control",
                capability="tabs.focus",
                dispatch_target="extension",
                execution_owner="browser_control",
                status="QUEUED",
                payload={"url": "https://source1.example.test"},
                evidence=[],
                provenance={},
                resume_metadata={},
                created_at=base_time + timedelta(seconds=11),
                updated_at=base_time + timedelta(seconds=11),
            )
        )
        db.commit()

        assigned = mission_ledger_service.next_intent(db, mission_id=mission_id, provider="browser_control")

        assert assigned.intent is not None
        assert assigned.intent.intent_id == "focus-source"
        surplus = db.get(MissionIntentRecord, "surplus-open")
        assert surplus is not None
        assert surplus.status == "SKIPPED"
        assert surplus.evidence[0]["kind"] == "source_cap"
    finally:
        db.close()


def test_next_intent_blocks_ungrounded_fill_before_browser_control():
    db = _session()
    try:
        mission_id = "mission-ledger-ungrounded-fill"
        mission_ledger_service.ensure_session(db, mission_id)
        db.add(
            MissionIntentRecord(
                intent_id="fill-without-selector",
                mission_id=mission_id,
                intent="fill",
                provider="browser_control",
                capability="browser.fill",
                dispatch_target="extension",
                execution_owner="browser_control",
                status="QUEUED",
                payload={"action_type": "fill", "value": "Rahul", "target_selector": ""},
                evidence=[],
                provenance={},
                resume_metadata={},
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        db.commit()

        assigned = mission_ledger_service.next_intent(db, mission_id=mission_id, provider="browser_control")

        assert assigned.intent is None
        assert assigned.status == "blocked"
        assert "ungrounded fill" in assigned.reason
        record = db.get(MissionIntentRecord, "fill-without-selector")
        assert record is not None
        assert record.status == "BLOCKED"
        assert record.evidence[0]["payload"]["guard"] == "ungrounded_browser_action"
    finally:
        db.close()
