from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cognitive_runtime.clarification import ClarificationEngine
from app.cognitive_runtime.lifecycle import MissionLifecycleAnalyzer
from app.cognitive_runtime.models import CognitiveEvidence, CognitiveMission, CognitiveState, EvidenceCollection
from app.cognitive_runtime.recovery import RecoveryStateEvaluator
from app.cognitive_runtime.replanning import ReplanningEvaluator
from app.cognitive_runtime.repository import SqlAlchemyCognitiveRuntimeRepository
from app.cognitive_runtime.service import CognitiveRuntimeService
from app.cognitive_runtime.snapshots import CognitiveSnapshotBuilder
from app.cognitive_runtime.state_machine import CognitiveStateMachine
from app.cognitive_runtime.transitions import TransitionEngine
from app.cognitive_runtime.waits import WaitStateEvaluator
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.mission.blueprint.repository import SqlAlchemyMissionBlueprintRepository
from app.mission.blueprint.readiness import BlueprintReadinessEvaluator
from app.mission.intelligence.blueprint_builder import MissionBlueprintBuilder
from app.models.db import MissionIntentRecord


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setattr(settings, "cognitive_runtime_v2", "shadow")
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")


def _evidence(evidence_id: str, evidence_type: str, *, payload=None, provenance=None) -> CognitiveEvidence:
    return CognitiveEvidence(
        evidence_id=evidence_id,
        mission_id="m1",
        source="mission_ledger",
        provider="test",
        evidence_type=evidence_type,
        payload=dict(payload or {}),
        provenance=dict(provenance or {}),
    )


def _blueprint(mission_id: str = "m1", goal: str = "Open the pricing page for Example CRM and verify it is visible."):
    return MissionBlueprintBuilder().build(mission_id=mission_id, user_goal=goal).blueprint


def test_transition_engine_accepts_legal_and_rejects_illegal_transitions():
    engine = TransitionEngine()
    legal = engine.transition(CognitiveState.READY, reason="blueprint_ready")
    illegal = engine.transition(CognitiveState.COMPLETED, reason="cannot_complete_from_ready")

    assert legal.legal is True
    assert illegal.legal is False
    assert engine.diagnostics().current_state == CognitiveState.READY
    assert engine.diagnostics().illegal_transition_count == 1


def test_state_machine_detects_user_wait_browser_wait_blocked_replanning_and_ready():
    machine = CognitiveStateMachine()

    assert machine.determine_state(clarification_required=True).state == CognitiveState.WAITING_USER
    assert machine.determine_state(wait_kind="browser").state == CognitiveState.WAITING_BROWSER
    assert machine.determine_state(blocked_nodes=["node1"]).state == CognitiveState.BLOCKED
    assert machine.determine_state(replanning_status="required").state == CognitiveState.REPLANNING
    assert machine.determine_state(ready_nodes=["node1"]).state == CognitiveState.READY


def test_clarification_engine_detects_unanswered_required_clarifications():
    blueprint = _blueprint(
        goal="Sign in to my account and open the dashboard.",
    )
    diagnostics = ClarificationEngine().evaluate(blueprint=blueprint, evidence=EvidenceCollection("m1"))

    assert diagnostics.required_count == 1
    assert diagnostics.urgency == "high"
    assert "blocking" in diagnostics.groups


def test_wait_state_evaluator_classifies_wait_kinds():
    collection = EvidenceCollection(
        "m1",
        (
            _evidence("ev1", "page_loading"),
            _evidence("ev2", "approval_required"),
            _evidence("ev3", "download_pending"),
        ),
    )
    diagnostics = WaitStateEvaluator().evaluate(collection)

    assert diagnostics.waiting is True
    assert {item["kind"] for item in diagnostics.active_waits} == {"browser", "user", "file"}


def test_recovery_and_replanning_are_passive_diagnostics():
    collection = EvidenceCollection(
        "m1",
        (
            _evidence("ev1", "failure"),
            _evidence("ev2", "recovery_available"),
            _evidence("ev3", "validation_failed"),
        ),
    )

    recovery = RecoveryStateEvaluator().evaluate(collection)
    replanning = ReplanningEvaluator().evaluate(collection, contradiction_count=1)

    assert recovery.classification == "recoverable"
    assert replanning.recommendation == "recommended"
    assert "contradictory_evidence" in replanning.reasons


def test_lifecycle_analyzer_reports_transition_counts_and_durations():
    mission = CognitiveMission(
        mission_id="m1",
        blueprint_id="bp1",
        blueprint_revision=1,
        created_at=datetime.now(UTC) - timedelta(seconds=10),
    )
    engine = TransitionEngine()
    engine.transition(CognitiveState.READY, reason="ready")
    engine.transition(CognitiveState.EXECUTING, reason="execute")
    engine.transition(CognitiveState.WAITING_BROWSER, reason="browser")
    summary = MissionLifecycleAnalyzer().analyze(mission=mission, transitions=engine.history)

    assert summary.mission_age_seconds >= 9
    assert summary.transition_count == 3
    assert summary.wait_duration_seconds == 1
    assert summary.execution_duration_seconds == 1


def test_snapshot_builder_combines_all_reasoning_sections():
    blueprint = _blueprint()
    readiness = BlueprintReadinessEvaluator().evaluate(blueprint)
    mission = CognitiveMission(mission_id="m1", blueprint_id=blueprint.blueprint_id, blueprint_revision=1)
    collection = EvidenceCollection("m1", (_evidence("ev1", "mission_understanding", payload={"subject": "define_target_state"}),))

    snapshot = CognitiveSnapshotBuilder().build(
        mission=mission,
        blueprint=blueprint,
        evidence=collection,
        readiness=readiness,
    )

    payload = snapshot.to_dict()
    assert payload["cognitive_state"]["state"] == "ready"
    assert payload["evidence_summary"]["coverage"]["total_requirements"] == 3
    assert "progress_summary" in payload
    assert "lifecycle_summary" in payload


def test_wave3_api_endpoints_are_read_only_and_feature_flagged(db_session, monkeypatch):
    blueprint = _blueprint("api-wave3")
    blueprint_repository = SqlAlchemyMissionBlueprintRepository(db_session)
    blueprint_repository.create(blueprint, reason="wave3 diagnostics test")
    blueprint_repository.save_readiness_snapshot(BlueprintReadinessEvaluator().evaluate(blueprint))
    service = CognitiveRuntimeService(SqlAlchemyCognitiveRuntimeRepository(db_session))
    service.create_runtime(mission_id="api-wave3", blueprint_id=blueprint.blueprint_id, blueprint_revision=1)
    service.attach_evidence(
        CognitiveEvidence(
            evidence_id="ev-api",
            mission_id="api-wave3",
            source="mission_ledger",
            provider="browser",
            evidence_type="page_loading",
            payload={},
            provenance={},
        )
    )

    def override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(fastapi_app)
        paths = [
            "/mission/api-wave3/cognitive/state",
            "/mission/api-wave3/cognitive/transitions",
            "/mission/api-wave3/cognitive/waits",
            "/mission/api-wave3/cognitive/clarifications",
            "/mission/api-wave3/cognitive/recovery",
            "/mission/api-wave3/cognitive/replanning",
            "/mission/api-wave3/cognitive/lifecycle",
            "/mission/api-wave3/cognitive/snapshot",
        ]
        responses = [client.get(path) for path in paths]
        monkeypatch.setattr(settings, "cognitive_runtime_v2", "off")
        disabled = client.get("/mission/api-wave3/cognitive/state")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["state"] == "waiting_browser"
    assert responses[2].json()["primary_wait"] == "browser"
    assert responses[-1].json()["wait_state"]["waiting"] is True
    assert disabled.status_code == 404
    assert db_session.query(MissionIntentRecord).count() == 0


def test_wave3_runtime_isolation_no_ledger_or_execution_mutation(db_session):
    service = CognitiveRuntimeService(SqlAlchemyCognitiveRuntimeRepository(db_session))
    service.create_runtime(mission_id="isolated", blueprint_id="bp1", blueprint_revision=1)
    state = service.cognitive_state(mission_id="isolated")

    assert state.state == CognitiveState.INITIALIZED
    assert db_session.query(MissionIntentRecord).count() == 0
