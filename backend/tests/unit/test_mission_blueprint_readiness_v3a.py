from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.mission.blueprint import (
    BlueprintDependency,
    BlueprintDependencyKind,
    BlueprintEvidence,
    BlueprintNode,
    BlueprintNodeKind,
    BlueprintReadinessEvaluator,
    BlueprintNodeReadiness,
    MissionBlueprintPersistenceService,
    SqlAlchemyMissionBlueprintRepository,
    create_blueprint,
)
from app.mission.blueprint.models import BlueprintEvidenceRequirement, ClarificationRequirement
from app.mission.intelligence.blueprint_builder import create_and_store_blueprint
from app.models.db import MissionBlueprintReadinessSnapshotRecord


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)(), engine


def _node(node_id: str, *, critical: bool = True, clarification: bool = False, prerequisite_evidence: bool = False) -> BlueprintNode:
    return BlueprintNode(
        node_id=node_id,
        objective=f"Objective {node_id}",
        kind=BlueprintNodeKind.GENERAL,
        metadata={"critical_path": critical},
        evidence_requirements=[
            BlueprintEvidenceRequirement(
                requirement_id=f"required_{node_id}",
                evidence_kind="source_available",
                subject=node_id,
                metadata={"prerequisite": prerequisite_evidence},
            )
        ],
        clarification_requirements=[
            ClarificationRequirement(
                clarification_id=f"clarify_{node_id}",
                question=f"Clarify {node_id}",
                required=True,
            )
        ] if clarification else [],
    )


def _evaluation(snapshot, node_id: str):
    return next(item for item in snapshot.evaluations if item.node_id == node_id)


def test_first_node_ready_and_dependent_node_waits(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    blueprint = create_blueprint(
        mission_id="readiness-basic",
        objective="Evaluate readiness",
        nodes=[_node("a"), _node("b")],
        dependencies=[
            BlueprintDependency(
                dependency_id="a_to_b",
                from_node_id="a",
                to_node_id="b",
            )
        ],
    )

    snapshot = BlueprintReadinessEvaluator().evaluate(blueprint)

    assert _evaluation(snapshot, "a").readiness == BlueprintNodeReadiness.READY
    assert _evaluation(snapshot, "a").expandable is True
    assert _evaluation(snapshot, "b").readiness == BlueprintNodeReadiness.WAITING
    assert "a" in _evaluation(snapshot, "b").dependency_reasons[0]


def test_dependency_satisfied_by_abstract_node_evidence(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    blueprint = create_blueprint(
        mission_id="readiness-evidence",
        objective="Evaluate readiness",
        nodes=[_node("a"), _node("b")],
        dependencies=[BlueprintDependency(dependency_id="a_to_b", from_node_id="a", to_node_id="b")],
    )

    snapshot = BlueprintReadinessEvaluator().evaluate(
        blueprint,
        evidence=[BlueprintEvidence(evidence_id="ev_a", evidence_kind="node_satisfied", subject="a")],
    )

    assert _evaluation(snapshot, "b").readiness == BlueprintNodeReadiness.READY
    assert _evaluation(snapshot, "b").expandable is True


def test_required_clarification_blocks_node(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    blueprint = create_blueprint(
        mission_id="readiness-clarification",
        objective="Evaluate readiness",
        nodes=[_node("needs_user", clarification=True)],
    )

    snapshot = BlueprintReadinessEvaluator().evaluate(blueprint)
    unblocked = BlueprintReadinessEvaluator().evaluate(
        blueprint,
        evidence=[
            BlueprintEvidence(
                evidence_id="clarified",
                evidence_kind="clarification_obtained",
                subject="clarify_needs_user",
            )
        ],
    )

    assert _evaluation(snapshot, "needs_user").readiness == BlueprintNodeReadiness.BLOCKED
    assert "clarify_needs_user" in _evaluation(snapshot, "needs_user").blocking_reasons[0]
    assert _evaluation(unblocked, "needs_user").readiness == BlueprintNodeReadiness.READY


def test_parallel_ready_nodes_are_reported(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    blueprint = create_blueprint(
        mission_id="readiness-parallel",
        objective="Evaluate readiness",
        nodes=[_node("critical", critical=True), _node("parallel", critical=False)],
    )

    snapshot = BlueprintReadinessEvaluator().evaluate(blueprint)

    assert "critical" in snapshot.critical_path_ready_nodes
    assert "parallel" in snapshot.parallel_ready_nodes
    assert set(snapshot.ready_nodes) == {"critical", "parallel"}


def test_prerequisite_evidence_requirement_blocks_until_available(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    blueprint = create_blueprint(
        mission_id="readiness-prereq-evidence",
        objective="Evaluate readiness",
        nodes=[_node("needs_source", prerequisite_evidence=True)],
    )

    waiting = BlueprintReadinessEvaluator().evaluate(blueprint)
    ready = BlueprintReadinessEvaluator().evaluate(
        blueprint,
        evidence=[
            BlueprintEvidence(
                evidence_id="source",
                evidence_kind="source_available",
                subject="needs_source",
            )
        ],
    )

    assert _evaluation(waiting, "needs_source").readiness == BlueprintNodeReadiness.WAITING
    assert "required_needs_source" in _evaluation(waiting, "needs_source").missing_evidence
    assert _evaluation(ready, "needs_source").readiness == BlueprintNodeReadiness.READY
    assert "source" in _evaluation(ready, "needs_source").supporting_evidence


def test_blocked_prerequisite_makes_dependent_node_unreachable(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    blueprint = create_blueprint(
        mission_id="readiness-unreachable",
        objective="Evaluate readiness",
        nodes=[_node("a"), _node("b")],
        dependencies=[BlueprintDependency(dependency_id="a_to_b", from_node_id="a", to_node_id="b")],
    )

    snapshot = BlueprintReadinessEvaluator().evaluate(
        blueprint,
        evidence=[BlueprintEvidence(evidence_id="blocked_a", evidence_kind="node_blocked", subject="a")],
    )

    assert _evaluation(snapshot, "b").readiness == BlueprintNodeReadiness.UNREACHABLE
    assert "b" in snapshot.unreachable_nodes


def test_optional_dependency_does_not_block_readiness(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    blueprint = create_blueprint(
        mission_id="readiness-optional",
        objective="Evaluate readiness",
        nodes=[_node("optional_source"), _node("target")],
        dependencies=[
            BlueprintDependency(
                dependency_id="optional_to_target",
                from_node_id="optional_source",
                to_node_id="target",
                kind=BlueprintDependencyKind.OPTIONAL,
                required=False,
            )
        ],
    )

    snapshot = BlueprintReadinessEvaluator().evaluate(blueprint)

    assert _evaluation(snapshot, "target").readiness == BlueprintNodeReadiness.READY


def test_readiness_snapshot_persistence_and_api(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        create_and_store_blueprint(
            mission_id="readiness-api",
            user_goal="Research best automation tools and create a report.",
            repository=repository,
        )
        service = MissionBlueprintPersistenceService(repository)
        snapshot = service.evaluate_readiness("readiness-api", persist=True)
        assert snapshot is not None
        assert db.query(MissionBlueprintReadinessSnapshotRecord).count() == 1

        def override_db():
            yield db

        fastapi_app.dependency_overrides[get_db] = override_db
        try:
            from fastapi.testclient import TestClient

            client = TestClient(fastapi_app)
            latest = client.get("/mission/readiness-api/blueprint/readiness")
            snapshots = client.get("/mission/readiness-api/blueprint/readiness/snapshots")
        finally:
            fastapi_app.dependency_overrides.clear()

        assert latest.status_code == 200, latest.text
        assert latest.json()["snapshot_id"] == snapshot.snapshot_id
        assert snapshots.status_code == 200, snapshots.text
        assert len(snapshots.json()["snapshots"]) == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_wave3a_keeps_runtime_v1_ledger_lifecycle_contract():
    from app.models.db import MissionIntentRecord

    intent_columns = {column.name for column in MissionIntentRecord.__table__.columns}

    assert "blueprint_readiness" not in intent_columns
    assert "blueprint_id" in intent_columns
    assert "blueprint_node_id" in intent_columns
    assert "blueprint_revision" in intent_columns
    assert "intent_id" in intent_columns
    assert "status" in intent_columns
