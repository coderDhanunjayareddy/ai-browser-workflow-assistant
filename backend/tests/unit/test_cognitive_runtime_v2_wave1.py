from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.cognitive_runtime import (
    CognitiveCheckpoint,
    CognitiveEvidence,
    CognitiveMission,
    CognitiveRuntimeController,
    CognitiveRuntimeService,
    EvidenceCollection,
    RuntimeVersion,
    SqlAlchemyCognitiveRuntimeRepository,
)
from app.cognitive_runtime.evidence import evidence_freshness_seconds, merge_evidence, normalize_confidence
from app.cognitive_runtime.metrics import compute_metrics
from app.cognitive_runtime.progress import compute_progress_snapshot
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.mission.blueprint.readiness import BlueprintEvidence, BlueprintReadinessEvaluator
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


def test_cognitive_models_validate_and_serialize():
    mission = CognitiveMission(mission_id="m1", blueprint_id="bp1", blueprint_revision=1)
    payload = mission.to_dict()

    assert payload["state"] == "initialized"
    assert CognitiveMission.from_dict(payload).mission_id == "m1"
    assert RuntimeVersion().is_compatible_with("2.1.0")


def test_evidence_collection_merge_deduplicates_and_tracks_provenance():
    evidence = CognitiveEvidence(
        evidence_id="ev1",
        mission_id="m1",
        source="mission_ledger",
        provider="browser",
        evidence_type="page_read",
        payload={"url": "https://example.com"},
        confidence=normalize_confidence(1.7),
        provenance={"intent_id": "intent1"},
    )
    collection = EvidenceCollection(mission_id="m1", evidence=(evidence,))
    merged = merge_evidence(collection, EvidenceCollection(mission_id="m1", evidence=(evidence,)))

    assert len(merged.evidence) == 1
    assert merged.provenance_lookup("intent_id", "intent1") == [evidence]
    assert evidence_freshness_seconds(evidence, now=datetime.now(UTC) + timedelta(seconds=10)) >= 9


def test_repository_crud_checkpoint_evidence_and_metrics(db_session):
    repository = SqlAlchemyCognitiveRuntimeRepository(db_session)
    service = CognitiveRuntimeService(repository)
    mission = service.create_runtime(mission_id="m1", blueprint_id="bp1", blueprint_revision=1)
    evidence = CognitiveEvidence(
        evidence_id="ev1",
        mission_id="m1",
        source="mission_ledger",
        provider="validation",
        evidence_type="node_satisfied",
        payload={"blueprint_node_id": "define_target_state"},
        confidence=0.8,
        provenance={"blueprint_node_id": "define_target_state"},
    )

    saved = service.attach_evidence(evidence)
    checkpoint = service.save_checkpoint("m1", {"state": mission.to_dict()})
    metrics = service.retrieve_metrics("m1")

    assert repository.get("m1") is not None
    assert saved.evidence_id == "ev1"
    restored = service.restore_checkpoint("m1", checkpoint.checkpoint_id)
    assert restored is not None
    assert restored.checkpoint_id == checkpoint.checkpoint_id
    assert restored.serialized_state == checkpoint.serialized_state
    assert metrics.evidence_count == 1
    assert metrics.confidence_average == 0.8
    assert repository.delete("m1") is True


def test_progress_snapshot_is_passive_and_uses_blueprint_readiness(db_session):
    result = MissionBlueprintBuilder().build(
        mission_id="progress-mission",
        user_goal="Open the pricing page for Example CRM and verify it is visible.",
    )
    readiness = BlueprintReadinessEvaluator().evaluate(
        result.blueprint,
        evidence=[
            BlueprintEvidence(
                evidence_id="bp-ev1",
                evidence_kind="node_satisfied",
                subject="define_target_state",
            )
        ],
    )
    evidence = [
        CognitiveEvidence(
            evidence_id="ev-node",
            mission_id="progress-mission",
            source="mission_ledger",
            provider="validation",
            evidence_type="node_satisfied",
            payload={},
            provenance={"blueprint_node_id": "define_target_state"},
        )
    ]

    snapshot = compute_progress_snapshot(blueprint=result.blueprint, evidence=evidence, readiness=readiness)

    assert snapshot.completed_nodes == ["define_target_state"]
    assert snapshot.ready_nodes == ["reach_target_state"]
    assert snapshot.completion_percentage > 0
    assert db_session.query(MissionIntentRecord).count() == 0


def test_controller_exposes_only_passive_operations(db_session):
    repository = SqlAlchemyCognitiveRuntimeRepository(db_session)
    controller = CognitiveRuntimeController(CognitiveRuntimeService(repository))

    mission = controller.initialize(mission_id="m1", blueprint_id="bp1", blueprint_revision=1)
    checkpoint = controller.checkpoint("m1", {"mission": mission.to_dict()})

    assert controller.restore("m1").checkpoint_id == checkpoint.checkpoint_id
    assert controller.metrics("m1").mission_id == "m1"
    assert db_session.query(MissionIntentRecord).count() == 0


def test_api_returns_disabled_when_feature_flag_off(monkeypatch, db_session):
    monkeypatch.setattr(settings, "cognitive_runtime_v2", "off")

    def override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        response = TestClient(fastapi_app).get("/mission/anything/cognitive")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "disabled" in response.json()["detail"]


def test_api_read_only_endpoints_return_runtime_state(db_session):
    blueprint_result = MissionBlueprintBuilder().build(
        mission_id="api-mission",
        user_goal="Open the pricing page for Example CRM and verify it is visible.",
    )
    blueprint_repository = SqlAlchemyMissionBlueprintRepository(db_session)
    blueprint_repository.create(blueprint_result.blueprint, reason="cognitive runtime api test")
    readiness = BlueprintReadinessEvaluator().evaluate(blueprint_result.blueprint)
    blueprint_repository.save_readiness_snapshot(readiness)

    service = CognitiveRuntimeService(SqlAlchemyCognitiveRuntimeRepository(db_session))
    service.create_runtime(
        mission_id="api-mission",
        blueprint_id=blueprint_result.blueprint.blueprint_id,
        blueprint_revision=blueprint_result.blueprint.revision,
    )
    service.attach_evidence(
        CognitiveEvidence(
            evidence_id="ev-api",
            mission_id="api-mission",
            source="mission_ledger",
            provider="browser",
            evidence_type="page_read",
            payload={"title": "Pricing"},
            confidence=0.75,
            provenance={"intent_id": "intent-api"},
        )
    )
    service.save_checkpoint("api-mission", {"phase": "shadow"})

    def override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(fastapi_app)
        root = client.get("/mission/api-mission/cognitive")
        checkpoints = client.get("/mission/api-mission/cognitive/checkpoints")
        evidence = client.get("/mission/api-mission/cognitive/evidence")
        progress = client.get("/mission/api-mission/cognitive/progress")
        metrics = client.get("/mission/api-mission/cognitive/metrics")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert root.status_code == 200
    assert checkpoints.json()["checkpoints"]
    assert evidence.json()["evidence"][0]["evidence_id"] == "ev-api"
    assert progress.json()["ready_nodes"] == ["define_target_state"]
    assert metrics.json()["evidence_count"] == 1
    assert db_session.query(MissionIntentRecord).count() == 0


def test_metrics_collection_counts_cognitive_evidence_only():
    metrics = compute_metrics(
        mission_id="m1",
        evidence=[
            CognitiveEvidence(
                evidence_id="ev1",
                mission_id="m1",
                source="human",
                provider="clarification",
                evidence_type="clarification_obtained",
                payload={},
                confidence=0.5,
            ),
            CognitiveEvidence(
                evidence_id="ev2",
                mission_id="m1",
                source="mission_intelligence",
                provider="planner",
                evidence_type="replan_requested",
                payload={},
                confidence=1.0,
            ),
        ],
    )

    assert metrics.evidence_count == 2
    assert metrics.clarification_count == 1
    assert metrics.replanning_count == 1
    assert metrics.confidence_average == 0.75
