from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cognitive_runtime.decision_engine import CognitiveDecisionContext, CognitiveDecisionEngine
from app.cognitive_runtime.decision_models import CognitiveDecisionType
from app.cognitive_runtime.models import CognitiveEvidence, EvidenceCollection
from app.cognitive_runtime.policy import DecisionPolicy
from app.cognitive_runtime.recommendations import RecommendationEngine
from app.cognitive_runtime.repository import SqlAlchemyCognitiveRuntimeRepository
from app.cognitive_runtime.service import CognitiveRuntimeService
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


def _evidence(evidence_type: str = "node_satisfied", *, payload=None, confidence=0.9) -> CognitiveEvidence:
    return CognitiveEvidence(
        evidence_id=f"ev-{evidence_type}",
        mission_id="m1",
        source="mission_ledger",
        provider="test",
        evidence_type=evidence_type,
        payload=dict(payload or {}),
        confidence=confidence,
        provenance={"intent_id": "intent1", "blueprint_node_id": "define_target_state"},
    )


def _blueprint(mission_id: str = "m1"):
    return MissionBlueprintBuilder().build(
        mission_id=mission_id,
        user_goal="Open the pricing page for Example CRM and verify it is visible.",
    ).blueprint


def _decide(*, evidence=None, readiness=None, blueprint=None, policy=None):
    collection = EvidenceCollection("m1", tuple(evidence or []))
    return CognitiveDecisionEngine().decide(
        CognitiveDecisionContext(
            blueprint=blueprint,
            readiness=readiness,
            evidence=collection,
            policy=DecisionPolicy.from_name(policy),
        )
    )


def test_continue_recommendation_when_ready_nodes_exist():
    result = _decide(readiness=SimpleNamespace(ready_nodes=["node1"], blocked_nodes=[], waiting_nodes=[]))

    assert result.decision.decision_type == CognitiveDecisionType.CONTINUE
    assert result.decision.metadata["execution_impact"] == "none"


def test_wait_recommendation_when_wait_evidence_exists():
    result = _decide(evidence=[_evidence("page_loading")])

    assert result.decision.decision_type == CognitiveDecisionType.WAIT
    assert "active_wait" in result.decision.rationale[0]


def test_clarification_recommendation_for_required_blueprint_question():
    blueprint = MissionBlueprintBuilder().build(
        mission_id="m1",
        user_goal="Sign in to my account and open the dashboard.",
    ).blueprint
    result = _decide(blueprint=blueprint)

    assert result.decision.decision_type == CognitiveDecisionType.REQUEST_USER


def test_recovery_recommendation_when_recovery_available():
    result = _decide(evidence=[_evidence("failure"), _evidence("recovery_available")])

    assert result.decision.decision_type == CognitiveDecisionType.RECOVER


def test_replanning_recommendation_when_required():
    result = _decide(evidence=[_evidence("blueprint_invalidated")])

    assert result.decision.decision_type == CognitiveDecisionType.REPLAN


def test_blocked_recommendation_when_recovery_is_blocked():
    result = _decide(evidence=[_evidence("node_blocked")])

    assert result.decision.decision_type == CognitiveDecisionType.BLOCKED


def test_complete_ready_recommendation_when_progress_is_complete():
    result = RecommendationEngine().recommend(
        mission_id="m1",
        evidence=EvidenceCollection("m1", ()),
        readiness=SimpleNamespace(ready_nodes=[], blocked_nodes=[], waiting_nodes=[]),
        diagnostics=SimpleNamespace(contradictions=[], freshness={}),
        wait_state=SimpleNamespace(waiting=False),
        clarification=SimpleNamespace(unanswered_count=0, required_count=0),
        recovery=SimpleNamespace(classification="unknown"),
        replanning=SimpleNamespace(recommendation="unnecessary"),
        progress=SimpleNamespace(completion_percentage=1.0),
        policy=DecisionPolicy.from_name("balanced"),
    )

    assert result.decision.decision_type == CognitiveDecisionType.COMPLETE_READY


def test_policy_differences_change_ranking_biases():
    signals = [
        _decide(evidence=[_evidence("validation_failed")], readiness=SimpleNamespace(ready_nodes=["node1"], blocked_nodes=[], waiting_nodes=[]), policy="conservative"),
        _decide(evidence=[_evidence("validation_failed")], readiness=SimpleNamespace(ready_nodes=["node1"], blocked_nodes=[], waiting_nodes=[]), policy="aggressive"),
    ]

    assert signals[0].decision.policy == "conservative"
    assert signals[1].decision.policy == "aggressive"
    assert DecisionPolicy.from_name("conservative").replan_bias > DecisionPolicy.from_name("aggressive").replan_bias


def test_confidence_explanation_and_alternatives_are_reported():
    result = _decide(
        evidence=[_evidence("validation_failed", confidence=0.6)],
        readiness=SimpleNamespace(ready_nodes=["node1"], blocked_nodes=[], waiting_nodes=[]),
    )

    assert 0.0 <= result.decision.confidence <= 1.0
    assert result.explanation.why
    assert result.ranked_signals
    assert result.explanation.confidence_explanation["normalized_score"] >= 0.0


def test_wave4_api_endpoints_are_read_only_and_feature_flagged(db_session, monkeypatch):
    blueprint = _blueprint("api-wave4")
    blueprint_repository = SqlAlchemyMissionBlueprintRepository(db_session)
    blueprint_repository.create(blueprint, reason="wave4 decision test")
    blueprint_repository.save_readiness_snapshot(BlueprintReadinessEvaluator().evaluate(blueprint))
    service = CognitiveRuntimeService(SqlAlchemyCognitiveRuntimeRepository(db_session))
    service.create_runtime(mission_id="api-wave4", blueprint_id=blueprint.blueprint_id, blueprint_revision=1)
    service.attach_evidence(
        CognitiveEvidence(
            evidence_id="ev-api",
            mission_id="api-wave4",
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
            "/mission/api-wave4/cognitive/decision",
            "/mission/api-wave4/cognitive/recommendations",
            "/mission/api-wave4/cognitive/decision/confidence",
            "/mission/api-wave4/cognitive/decision/explanation",
            "/mission/api-wave4/cognitive/decision/policy?policy=conservative",
            "/mission/api-wave4/cognitive/decision/alternatives",
        ]
        responses = [client.get(path) for path in paths]
        monkeypatch.setattr(settings, "cognitive_runtime_v2", "off")
        disabled = client.get("/mission/api-wave4/cognitive/decision")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["decision_type"] == "wait"
    assert responses[2].json()["confidence"] >= 0.0
    assert responses[3].json()["explanation"]["assumptions"]
    assert responses[4].json()["name"] == "conservative"
    assert disabled.status_code == 404
    assert db_session.query(MissionIntentRecord).count() == 0


def test_wave4_runtime_isolation_no_ledger_or_execution_mutation(db_session):
    service = CognitiveRuntimeService(SqlAlchemyCognitiveRuntimeRepository(db_session))
    service.create_runtime(mission_id="isolated", blueprint_id="bp1", blueprint_revision=1)
    decision = service.cognitive_decision(mission_id="isolated", blueprint=None)

    assert decision.decision.decision_type == CognitiveDecisionType.UNKNOWN
    assert db_session.query(MissionIntentRecord).count() == 0
