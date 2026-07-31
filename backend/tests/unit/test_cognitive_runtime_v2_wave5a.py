from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cognitive_runtime.comparison import DecisionAgreementEngine
from app.cognitive_runtime.comparison_metrics import compute_comparison_metrics
from app.cognitive_runtime.comparison_models import DecisionComparison
from app.cognitive_runtime.comparison_repository import SqlAlchemyDecisionComparisonRepository
from app.cognitive_runtime.comparison_report import ComparisonReportBuilder
from app.cognitive_runtime.comparison_service import DecisionComparisonService
from app.cognitive_runtime.models import CognitiveEvidence
from app.cognitive_runtime.repository import SqlAlchemyCognitiveRuntimeRepository
from app.cognitive_runtime.service import CognitiveRuntimeService
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.mission.blueprint.repository import SqlAlchemyMissionBlueprintRepository
from app.mission.blueprint.readiness import BlueprintReadinessEvaluator
from app.mission.intelligence.blueprint_builder import MissionBlueprintBuilder
from app.models.db import CognitiveDecisionComparisonRecord, MissionIntentRecord
from app.orchestrator.workflow_orchestrator import WorkflowOrchestrator
from app.schemas.response import AnalyzeResponse, SuggestedAction


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


def _recommendation(decision_type: str, confidence: float = 0.82, reason: str = "test_signal"):
    return SimpleNamespace(
        decision=SimpleNamespace(
            decision_type=SimpleNamespace(value=decision_type),
            confidence=confidence,
            rationale=[reason],
        ),
        explanation=SimpleNamespace(to_dict=lambda: {"why": [reason]}),
        ranked_signals=[],
    )


def _service(db_session) -> DecisionComparisonService:
    return DecisionComparisonService(SqlAlchemyDecisionComparisonRepository(db_session))


def _blueprint(mission_id: str):
    return MissionBlueprintBuilder().build(
        mission_id=mission_id,
        user_goal="Research AI browser automation tools and produce a comparison table.",
    ).blueprint


def test_agreement_engine_exact_partial_and_disagreement():
    engine = DecisionAgreementEngine()

    exact = engine.compare(runtime_decision="WAIT", cognitive_decision="wait")
    partial = engine.compare(runtime_decision="WAIT", cognitive_decision="request_user")
    disagreement = engine.compare(runtime_decision="WAIT", cognitive_decision="replan")

    assert exact.agreement.value == "exact"
    assert partial.agreement.value == "partial"
    assert disagreement.agreement.value == "disagreement"
    assert disagreement.disagreement_type == "wait_vs_replan"


def test_comparison_service_persists_runtime_and_cognitive_decisions(db_session):
    saved = _service(db_session).record(
        mission_id="m5a",
        intent_id="intent1",
        blueprint_node_id="node1",
        runtime_decision="WAIT",
        runtime_reason="Runtime V1 waited.",
        cognitive=_recommendation("request_user", 0.9, "clarification_required"),
        recommendation_latency_ms=3.2,
    )
    latest = _service(db_session).latest("m5a")

    assert saved.agreement == "partial"
    assert latest is not None
    assert latest.runtime_decision == "WAIT"
    assert latest.cognitive_decision == "REQUEST_USER"
    assert latest.metadata["runtime_v1_wins"] is True
    assert db_session.query(CognitiveDecisionComparisonRecord).count() == 1


def test_metrics_track_confidence_and_false_positive_candidates():
    comparisons = [
        DecisionComparison("m", "WAIT", "WAIT", "exact", 0.8, "r", "c", {}),
        DecisionComparison("m", "WAIT", "REPLAN", "disagreement", 0.91, "r", "c", {}),
        DecisionComparison("m", "FAILED", "CONTINUE", "disagreement", 0.77, "r", "c", {}),
    ]

    metrics = compute_comparison_metrics(comparisons)

    assert metrics["total_comparisons"] == 3
    assert metrics["high_confidence_disagreement"] == 2
    assert metrics["false_positive_candidates"][0]["cognitive_decision"] == "REPLAN"
    assert metrics["false_negative_candidates"][0]["runtime_decision"] == "FAILED"
    assert metrics["average_confidence"] > 0.8


def test_report_builder_produces_migration_readiness_and_hotspots():
    report = ComparisonReportBuilder().build(
        mission_id="m",
        comparisons=[
            DecisionComparison("m", "WAIT", "WAIT", "exact", 0.9, "r", "c", {}),
            DecisionComparison("m", "WAIT", "REPLAN", "disagreement", 0.92, "r", "c", {}),
        ],
    )

    assert report["summary"]["runtime_boundary"].startswith("Runtime V1 always wins")
    assert report["disagreement_hotspots"][0]["transition"] == "WAIT->REPLAN"
    assert report["migration_readiness"]["execution_authority"] == "runtime_v1"


def test_comparison_api_endpoints_are_read_only_and_feature_flagged(db_session, monkeypatch):
    _service(db_session).record(
        mission_id="api-5a",
        runtime_decision="CONTINUE",
        runtime_reason="Runtime V1 produced work.",
        cognitive=_recommendation("continue", 0.88, "ready_nodes_available"),
    )

    def override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(fastapi_app)
        paths = [
            "/mission/api-5a/cognitive/comparison",
            "/mission/api-5a/cognitive/comparison/history",
            "/mission/api-5a/cognitive/comparison/metrics",
            "/mission/api-5a/cognitive/comparison/report",
            "/mission/api-5a/cognitive/comparison/disagreements",
        ]
        responses = [client.get(path) for path in paths]
        monkeypatch.setattr(settings, "cognitive_runtime_v2", "off")
        disabled = client.get("/mission/api-5a/cognitive/comparison/history")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["agreement"] == "exact"
    assert responses[1].json()["comparisons"][0]["runtime_decision"] == "CONTINUE"
    assert responses[2].json()["metrics"]["overall_agreement"] == 1.0
    assert responses[3].json()["migration_readiness"]["execution_authority"] == "runtime_v1"
    assert responses[4].json()["disagreements"] == []
    assert disabled.status_code == 404
    assert db_session.query(MissionIntentRecord).count() == 0


def test_orchestrator_shadow_hook_records_comparison_without_changing_response(db_session):
    mission_id = "hook-5a"
    blueprint = _blueprint(mission_id)
    blueprint_repo = SqlAlchemyMissionBlueprintRepository(db_session)
    blueprint_repo.create(blueprint, reason="wave5a hook test")
    blueprint_repo.save_readiness_snapshot(BlueprintReadinessEvaluator().evaluate(blueprint))
    cognitive = CognitiveRuntimeService(SqlAlchemyCognitiveRuntimeRepository(db_session))
    cognitive.create_runtime(mission_id=mission_id, blueprint_id=blueprint.blueprint_id, blueprint_revision=1)
    cognitive.attach_evidence(
        CognitiveEvidence(
            evidence_id="ev-hook",
            mission_id=mission_id,
            source="mission_ledger",
            provider="test",
            evidence_type="page_loading",
            payload={},
            provenance={},
        )
    )
    response = AnalyzeResponse(
        session_id=mission_id,
        analysis="Runtime V1 waits.",
        outcome_kind="wait",
        suggested_actions=[],
    )
    before = response.model_dump()

    WorkflowOrchestrator(mission_id, db_session)._record_cognitive_decision_comparison_shadow(result=response)

    assert response.model_dump() == before
    comparison = _service(db_session).latest(mission_id)
    assert comparison is not None
    assert comparison.runtime_decision == "WAIT"
    assert comparison.metadata["execution_impact"] == "none"
    assert db_session.query(MissionIntentRecord).count() == 0


def test_orchestrator_shadow_hook_is_noop_when_flag_is_off(db_session, monkeypatch):
    monkeypatch.setattr(settings, "cognitive_runtime_v2", "off")
    response = AnalyzeResponse(
        session_id="off-5a",
        analysis="Runtime V1 continues.",
        suggested_actions=[
            SuggestedAction(
                action_id="a1",
                action_type="navigate",
                target_selector="",
                value="https://example.com",
                description="Navigate",
                reasoning="test",
                confidence=0.8,
                safety_level="safe",
            )
        ],
    )

    WorkflowOrchestrator("off-5a", db_session)._record_cognitive_decision_comparison_shadow(result=response)

    assert _service(db_session).history("off-5a") == []
