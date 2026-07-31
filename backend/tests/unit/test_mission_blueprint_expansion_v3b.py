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
from app.mission.blueprint.expansion import KNOWLEDGE_EXTRACTION_DISPATCH_TARGET, compile_node_to_intents
from app.mission.blueprint.models import BlueprintExpansionRule
from app.models.db import MissionBlueprintExpansionRecord, MissionIntentRecord
from app.services import mission_ledger_service


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


def _open_result_node(index: int = 1) -> BlueprintNode:
    return BlueprintNode(
        node_id=f"open_result_{index}",
        objective=f"Open ranked result {index}",
        kind=BlueprintNodeKind.OPEN_RESULT,
        owner_capabilities=["Browser"],
        metadata={"critical_path": False},
    )


def _extract_fields_node(index: int = 1) -> BlueprintNode:
    return BlueprintNode(
        node_id=f"extract_fields_{index}",
        objective=f"Extract fields from ranked result page {index}",
        kind=BlueprintNodeKind.FIELD_EXTRACTION,
        owner_capabilities=["Knowledge Extraction"],
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


def test_open_result_expansion_uses_ranked_result_from_ledger(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        mission_id = "expand-ranked-open"
        repository = SqlAlchemyMissionBlueprintRepository(db)
        service = MissionBlueprintPersistenceService(repository)
        blueprint = service.create(
            mission_id=mission_id,
            objective="Research sources",
            nodes=[_open_result_node(2)],
        )
        mission_ledger_service.ensure_session(db, mission_id)
        db.add(
            MissionIntentRecord(
                intent_id="rank-intent",
                mission_id=mission_id,
                intent="rank_records",
                provider="validation",
                capability="validation",
                dispatch_target="validation",
                execution_owner="validation",
                status="COMPLETED",
                payload={},
                evidence=[
                    {
                        "payload": {
                            "ranked_results": [
                                {
                                    "rank": 1,
                                    "title": "11 Best AI Browser Agents in 2026",
                                    "url": "https://www.firecrawl.dev/blog/best-browser-agents",
                                },
                                {
                                    "rank": 2,
                                    "title": "Top 12 Browser Automation Tools in 2026",
                                    "url": "https://www.browserstack.com/guide/best-browser-automation-tool",
                                }
                            ]
                        }
                    }
                ],
                blueprint_id=blueprint.blueprint_id,
                blueprint_node_id="rank_results",
                blueprint_revision=blueprint.revision,
            )
        )
        db.commit()
        readiness = BlueprintReadinessEvaluator().evaluate(blueprint)

        BlueprintExpansionEngine(db=db, repository=repository).expand_ready_nodes(
            mission_id=mission_id,
            readiness=readiness,
        )

        record = (
            db.query(MissionIntentRecord)
            .filter(MissionIntentRecord.mission_id == mission_id)
            .filter(MissionIntentRecord.blueprint_node_id == "open_result_2")
            .one()
        )
        assert record.intent == "open_new_tab"
        assert record.payload["value"] == "https://www.browserstack.com/guide/best-browser-automation-tool"
        assert record.payload["url"] == "https://www.browserstack.com/guide/best-browser-automation-tool"
        assert record.payload["title"] == "Top 12 Browser Automation Tools in 2026"
        assert record.payload["rank"] == 2
        assert record.payload["blueprint_id"] == blueprint.blueprint_id
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_blueprint_knowledge_intents_use_registered_dispatch_target(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        service = MissionBlueprintPersistenceService(repository)
        blueprint = service.create(
            mission_id="expand-knowledge-target",
            objective="Research sources",
            nodes=[_open_result_node(1), _extract_fields_node(1)],
        )
        read_node = BlueprintNode(
            node_id="read_page_1",
            objective="Read ranked result page 1",
            kind=BlueprintNodeKind.PAGE_READ,
            owner_capabilities=["Knowledge Extraction"],
            expansion_template={
                "provider": "knowledge_extraction",
                "action": "read_page",
            },
        )

        read_directive = compile_node_to_intents(blueprint, read_node)[0]
        extract_directive = compile_node_to_intents(blueprint, _extract_fields_node(1))[0]

        assert read_directive.owner == "knowledge_extraction"
        assert read_directive.dispatch_target == KNOWLEDGE_EXTRACTION_DISPATCH_TARGET
        assert extract_directive.owner == "knowledge_extraction"
        assert extract_directive.dispatch_target == KNOWLEDGE_EXTRACTION_DISPATCH_TARGET
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()
