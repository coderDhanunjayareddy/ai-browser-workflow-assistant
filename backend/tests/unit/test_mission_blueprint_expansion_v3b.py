from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.mission.blueprint import (
    BlueprintExpansionEngine,
    BlueprintNode,
    BlueprintNodeKind,
    BlueprintReadinessEvaluator,
    MissionBlueprintPersistenceService,
    SqlAlchemyMissionBlueprintRepository,
)
from app.mission.blueprint.models import BlueprintExpansionRule
from app.models.db import MissionBlueprintExpansionRecord, MissionIntentRecord


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)(), engine


def _discover_node() -> BlueprintNode:
    return BlueprintNode(
        node_id="discover_sources",
        objective="Discover relevant sources",
        kind=BlueprintNodeKind.DISCOVERY,
        owner_capabilities=["Search", "Browser"],
        expansion_rules=[
            BlueprintExpansionRule(
                rule_id="expand_discover_sources",
                capability="Search",
                intent_template="discover_sources",
            )
        ],
        metadata={"critical_path": True},
    )


def _report_node() -> BlueprintNode:
    return BlueprintNode(
        node_id="create_report",
        objective="Create final report",
        kind=BlueprintNodeKind.REPORTING,
        owner_capabilities=["Report Generation"],
        expansion_rules=[
            BlueprintExpansionRule(
                rule_id="expand_create_report",
                capability="Report Generation",
                intent_template="create_report",
            )
        ],
        metadata={"critical_path": False},
    )


def test_expands_only_ready_nodes_into_queued_ledger_intents(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        service = MissionBlueprintPersistenceService(repository)
        blueprint = service.create(
            mission_id="expand-ready",
            objective="Research sources",
            nodes=[_discover_node()],
        )
        readiness = BlueprintReadinessEvaluator().evaluate(blueprint)

        result = BlueprintExpansionEngine(db=db, repository=repository).expand_ready_nodes(
            mission_id="expand-ready",
            readiness=readiness,
        )

        records = db.query(MissionIntentRecord).filter(MissionIntentRecord.mission_id == "expand-ready").all()
        assert result.expanded_nodes == ["discover_sources"]
        assert len(result.generated_intent_ids) == 3
        assert len(records) == 3
        assert {record.status for record in records} == {"QUEUED"}
        assert {record.blueprint_id for record in records} == {blueprint.blueprint_id}
        assert {record.blueprint_node_id for record in records} == {"discover_sources"}
        assert {record.blueprint_revision for record in records} == {1}
        assert db.query(MissionBlueprintExpansionRecord).count() == 1
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_expansion_is_idempotent_and_does_not_duplicate_intents(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        service = MissionBlueprintPersistenceService(repository)
        blueprint = service.create(
            mission_id="expand-idempotent",
            objective="Research sources",
            nodes=[_discover_node()],
        )
        readiness = BlueprintReadinessEvaluator().evaluate(blueprint)
        engine_ = BlueprintExpansionEngine(db=db, repository=repository)

        first = engine_.expand_ready_nodes(mission_id="expand-idempotent", readiness=readiness)
        second = engine_.expand_ready_nodes(mission_id="expand-idempotent", readiness=readiness)

        assert db.query(MissionIntentRecord).filter(MissionIntentRecord.mission_id == "expand-idempotent").count() == 3
        assert db.query(MissionBlueprintExpansionRecord).count() == 1
        assert first.generated_intent_ids == second.generated_intent_ids
        assert second.node_results[0].skipped_reason == "already_expanded"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_not_ready_node_is_not_expanded(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        service = MissionBlueprintPersistenceService(repository)
        service.create(
            mission_id="expand-pending",
            objective="Research sources",
            nodes=[_discover_node(), _report_node()],
        )
        readiness = repository.latest_readiness_snapshot("expand-pending")

        result = BlueprintExpansionEngine(db=db, repository=repository).expand_ready_nodes(
            mission_id="expand-pending",
            readiness=readiness,
        )

        assert result.expanded_nodes == []
        assert set(result.pending_nodes) == {"discover_sources", "create_report"}
        assert db.query(MissionIntentRecord).count() == 0
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_expansion_history_api_exposes_generated_intents(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        service = MissionBlueprintPersistenceService(repository)
        blueprint = service.create(
            mission_id="expand-api",
            objective="Research sources",
            nodes=[_discover_node()],
        )
        readiness = BlueprintReadinessEvaluator().evaluate(blueprint)
        BlueprintExpansionEngine(db=db, repository=repository).expand_ready_nodes(
            mission_id="expand-api",
            readiness=readiness,
        )

        def override_db():
            yield db

        fastapi_app.dependency_overrides[get_db] = override_db
        try:
            from fastapi.testclient import TestClient

            response = TestClient(fastapi_app).get("/mission/expand-api/blueprint/expansions")
        finally:
            fastapi_app.dependency_overrides.clear()

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["expanded_nodes"] == ["discover_sources"]
        assert len(payload["generated_intent_ids"]) == 3
        assert payload["expansions"][0]["diagnostics"]["execution_impact"] == "queued_only_no_dispatch"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_wave3b_adds_references_without_changing_ledger_lifecycle(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        service = MissionBlueprintPersistenceService(repository)
        blueprint = service.create(
            mission_id="expand-lifecycle",
            objective="Research sources",
            nodes=[_discover_node()],
        )
        readiness = BlueprintReadinessEvaluator().evaluate(blueprint)
        BlueprintExpansionEngine(db=db, repository=repository).expand_ready_nodes(
            mission_id="expand-lifecycle",
            readiness=readiness,
        )
        record = db.query(MissionIntentRecord).first()

        assert record.status == "QUEUED"
        assert record.dispatched_at is None
        assert record.completed_at is None
        assert record.evidence == []
        assert record.blueprint_node_id == "discover_sources"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
