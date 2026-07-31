from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cognitive_runtime.confidence import ConfidenceEvaluator
from app.cognitive_runtime.contradiction import ContradictionDetector
from app.cognitive_runtime.diagnostics import build_diagnostics
from app.cognitive_runtime.freshness import FreshnessEvaluator
from app.cognitive_runtime.fusion import EvidenceFusionEngine
from app.cognitive_runtime.interpreter import EvidenceInterpreter
from app.cognitive_runtime.models import CognitiveEvidence, EvidenceCollection
from app.cognitive_runtime.repository import SqlAlchemyCognitiveRuntimeRepository
from app.cognitive_runtime.requirements import EvidenceRequirementMatcher
from app.cognitive_runtime.service import CognitiveRuntimeService
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.mission.blueprint.repository import SqlAlchemyMissionBlueprintRepository
from app.mission.intelligence.blueprint_builder import MissionBlueprintBuilder
from app.models.db import MissionIntentRecord


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


def _evidence(
    evidence_id: str,
    *,
    mission_id: str = "m1",
    evidence_type: str = "mission_understanding",
    provider: str = "validation",
    confidence: float = 0.9,
    payload: dict | None = None,
    provenance: dict | None = None,
    timestamp: datetime | None = None,
) -> CognitiveEvidence:
    return CognitiveEvidence(
        evidence_id=evidence_id,
        mission_id=mission_id,
        source="Mission_Ledger",
        provider=provider,
        evidence_type=evidence_type,
        payload=dict(payload or {"subject": "define_target_state"}),
        confidence=confidence,
        timestamp=timestamp or datetime.now(UTC),
        provenance=dict(provenance or {"intent_id": "intent1", "blueprint_node_id": "define_target_state"}),
    )


def _blueprint(mission_id: str = "m1"):
    return MissionBlueprintBuilder().build(
        mission_id=mission_id,
        user_goal="Open the pricing page for Example CRM and verify it is visible.",
    ).blueprint


def test_interpreter_normalizes_and_classifies_evidence():
    evidence = _evidence("ev1", provider="Browser_Control", evidence_type="FIELD_EXTRACTION", confidence=1.0)
    normalized = EvidenceInterpreter().normalize(evidence)

    assert normalized.provider == "browser_control"
    assert normalized.evidence_type == "field_extraction"
    assert normalized.confidence == 1.0
    assert EvidenceInterpreter().classify(normalized) == "semantic"


def test_fusion_collapses_duplicates_and_preserves_provenance():
    first = _evidence("ev1", confidence=0.6, payload={"subject": "define_target_state", "value": "pricing"})
    second = _evidence("ev2", confidence=0.95, payload={"subject": "define_target_state", "value": "pricing"})
    result = EvidenceFusionEngine(provider_weights={"validation": 0.9}).fuse([
        EvidenceCollection("m1", (first,)),
        EvidenceCollection("m1", (second,)),
    ])

    assert result.duplicates_collapsed == 1
    assert [item.evidence_id for item in result.collection.evidence] == ["ev2"]
    assert result.provider_distribution == {"validation": 1}
    assert result.confidence_by_evidence["ev2"] <= 0.9
    assert result.provenance_graph["ev2"]


def test_confidence_uses_freshness_corroboration_and_provenance():
    evidence = _evidence("ev1", confidence=0.8)
    score = ConfidenceEvaluator().evaluate(evidence, freshness_factor=0.5, corroboration_count=3)

    assert 0.0 <= score.normalized_confidence <= 1.0
    assert score.corroboration_factor > 0.7
    assert score.provenance_factor > 0.4


def test_freshness_detects_stale_evidence():
    evidence = _evidence(
        "ev1",
        timestamp=datetime.now(UTC) - timedelta(seconds=120),
        payload={"expiration_seconds": 30},
    )
    report = FreshnessEvaluator().evaluate(evidence)

    assert report.stale is True
    assert report.freshness_score == 0.0


def test_contradiction_detector_reports_conflicting_claims():
    collection = EvidenceCollection(
        "m1",
        (
            _evidence("ev1", payload={"claims": {"price": "$10"}}, provenance={"blueprint_node_id": "extract_records"}),
            _evidence("ev2", payload={"claims": {"price": "$20"}}, provenance={"blueprint_node_id": "extract_records"}),
        ),
    )
    reports = ContradictionDetector().detect(collection)

    assert len(reports) == 1
    assert reports[0].field == "price"
    assert reports[0].reason == "conflicting_field_values"


def test_requirement_matcher_reports_satisfied_missing_and_partial():
    blueprint = _blueprint()
    node = blueprint.nodes[0]
    satisfied = EvidenceRequirementMatcher().match(node, EvidenceCollection("m1", (_evidence("ev1"),)))
    missing = EvidenceRequirementMatcher().match(node, EvidenceCollection("m1", ()))

    assert satisfied.satisfied_requirements[0].requirement_id == "evidence_define_target_state"
    assert missing.missing_requirements[0].status == "missing"


def test_diagnostics_reports_coverage_missing_confidence_and_distribution():
    blueprint = _blueprint()
    collection = EvidenceCollection("m1", (_evidence("ev1"),))
    diagnostics = build_diagnostics(blueprint=blueprint, collection=collection)

    assert diagnostics.evidence_count == 1
    assert diagnostics.coverage["total_requirements"] == 3
    assert diagnostics.coverage["satisfied_requirements"] == 1
    assert diagnostics.missing_evidence
    assert diagnostics.confidence["ev1"]["normalized_confidence"] > 0
    assert diagnostics.provider_distribution == {"validation": 1}


def test_interpretation_combines_fusion_requirements_contradictions_and_diagnostics():
    blueprint = _blueprint()
    collection = EvidenceCollection("m1", (_evidence("ev1"), _evidence("ev1"),))
    interpretation = EvidenceInterpreter().interpret(blueprint=blueprint, collection=collection)

    assert interpretation.duplicate_evidence == 1
    assert interpretation.requirement_matches
    assert interpretation.diagnostics["coverage"]["total_requirements"] == 3


def test_wave2_api_endpoints_are_read_only_and_feature_flagged(db_session, monkeypatch):
    blueprint = _blueprint("api-wave2")
    blueprint_repository = SqlAlchemyMissionBlueprintRepository(db_session)
    blueprint_repository.create(blueprint, reason="wave2 diagnostics test")
    service = CognitiveRuntimeService(SqlAlchemyCognitiveRuntimeRepository(db_session))
    service.create_runtime(mission_id="api-wave2", blueprint_id=blueprint.blueprint_id, blueprint_revision=1)
    service.attach_evidence(_evidence("ev-api", mission_id="api-wave2"))

    def override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(fastapi_app)
        diagnostics = client.get("/mission/api-wave2/cognitive/evidence/diagnostics")
        coverage = client.get("/mission/api-wave2/cognitive/evidence/coverage")
        confidence = client.get("/mission/api-wave2/cognitive/evidence/confidence")
        contradictions = client.get("/mission/api-wave2/cognitive/evidence/contradictions")
        monkeypatch.setattr(settings, "cognitive_runtime_v2", "off")
        disabled = client.get("/mission/api-wave2/cognitive/evidence/diagnostics")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert diagnostics.status_code == 200
    assert coverage.json()["coverage"]["total_requirements"] == 3
    assert "ev-api" in confidence.json()["confidence"]
    assert contradictions.json()["contradictions"] == []
    assert disabled.status_code == 404
    assert db_session.query(MissionIntentRecord).count() == 0


def test_wave2_runtime_isolation_no_ledger_blueprint_or_planner_mutation(db_session):
    service = CognitiveRuntimeService(SqlAlchemyCognitiveRuntimeRepository(db_session))
    service.create_runtime(mission_id="isolated", blueprint_id="bp1", blueprint_revision=1)
    service.attach_evidence(_evidence("ev1", mission_id="isolated"))
    interpretation = service.interpret_evidence(mission_id="isolated", blueprint=None)

    assert interpretation.mission_id == "isolated"
    assert db_session.query(MissionIntentRecord).count() == 0
