from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.mission.intelligence.blueprint_builder import (
    MissionBlueprintBuilder,
    MissionType,
    create_and_store_blueprint,
)
from app.mission.blueprint.repository import SqlAlchemyMissionBlueprintRepository


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False)(), engine


def test_research_goal_creates_research_blueprint(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-research",
        user_goal=(
            "Open Google Search and search for best AI browser automation tools 2026. "
            "Open the top 5 relevant results, read each page, extract tool, purpose, "
            "pricing, limitation, URL, and return a clean comparison table only."
        ),
    )

    assert result.mission_type == MissionType.RESEARCH
    assert "Search" in result.capabilities.capabilities
    assert "Knowledge Extraction" in result.capabilities.capabilities
    assert "Validation" in result.capabilities.capabilities
    assert [node.node_id for node in result.blueprint.nodes] == [
        "clarify_requirements",
        "define_research_target",
        "discover_sources",
        "collect_candidates",
        "select_sources",
        "read_sources",
        "extract_information",
        "validate_coverage",
        "create_report",
    ]
    assert "top_n:5" in result.blueprint.constraints
    assert "output_table_only" in result.blueprint.constraints
    assert result.blueprint.metadata["mission_classification"]["primary_type"] == "research"


def test_navigation_goal_creates_target_state_graph(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-navigation",
        user_goal="Open the pricing page for Example CRM and verify the pricing page is visible.",
    )

    assert result.mission_type == MissionType.NAVIGATION
    assert [node.node_id for node in result.blueprint.nodes] == [
        "define_target_state",
        "reach_target_state",
        "verify_target_state",
    ]
    assert result.capabilities.capabilities == ["Browser", "Validation"]


def test_data_extraction_goal_creates_extraction_graph(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-extract",
        user_goal="Extract records from this directory table with columns name, pricing, url.",
    )

    assert result.mission_type == MissionType.DATA_EXTRACTION
    assert "extract_records" in [node.node_id for node in result.blueprint.nodes]
    assert "structured_artifact_delivered" in result.blueprint.success_criteria
    assert "Knowledge Extraction" in result.capabilities.capabilities


def test_file_processing_goal_creates_file_graph(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-file",
        user_goal="Process the uploaded CSV file and create a validated summary artifact.",
    )

    assert result.mission_type == MissionType.FILE_PROCESSING
    assert [node.node_id for node in result.blueprint.nodes] == [
        "define_file_requirement",
        "access_file",
        "process_file",
        "validate_file_result",
        "deliver_file_result",
    ]
    assert "File Processing" in result.capabilities.capabilities


def test_dependency_graph_is_sequential_acyclic_and_critical(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-deps",
        user_goal="Research best browser automation tools and create a report.",
    )

    assert result.dependencies.sequential_dependencies
    assert result.dependencies.critical_path
    assert result.dependencies.evidence_dependencies
    assert len(result.blueprint.dependencies) == len(result.blueprint.nodes) - 1


def test_clarification_requirements_are_recorded_not_asked(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-clarify",
        user_goal="Sign in to my account and open the dashboard.",
    )

    clarifications = result.blueprint.metadata["clarification_requirements"]
    assert clarifications
    assert clarifications[0]["clarification_id"] == "clarify_account_or_authentication_context"
    assert result.blueprint.nodes[0].node_id == "clarify_requirements"


def test_create_and_store_blueprint_persists_revision_one(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        result = create_and_store_blueprint(
            mission_id="wave2-store",
            user_goal="Research best AI automation tools and create a table.",
            repository=repository,
        )

        loaded = repository.get("wave2-store")
        revisions = repository.list_revisions("wave2-store")

        assert loaded is not None
        assert loaded.blueprint_id == result.blueprint.blueprint_id
        assert revisions[0]["revision"] == 1
        assert loaded.metadata["wave"] == "mission_blueprint_v1_wave2"
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_read_api_exposes_wave2_analysis_metadata(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    db, engine = _session()
    try:
        repository = SqlAlchemyMissionBlueprintRepository(db)
        create_and_store_blueprint(
            mission_id="wave2-api",
            user_goal="Extract records from a documentation table and deliver a structured artifact.",
            repository=repository,
        )

        def override_db():
            yield db

        fastapi_app.dependency_overrides[get_db] = override_db
        try:
            from fastapi.testclient import TestClient

            response = TestClient(fastapi_app).get("/mission/wave2-api/blueprint")
        finally:
            fastapi_app.dependency_overrides.clear()

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["mission_analysis"]["primary_objective"]
        assert "Knowledge Extraction" in payload["capability_requirements"]["capabilities"]
        assert payload["risk_summary"]["risks"]
        assert payload["dependency_graph"]["sequential_dependencies"]
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_wave2_does_not_modify_runtime_v1_ledger_contract():
    from app.models.db import MissionIntentRecord

    intent_columns = {column.name for column in MissionIntentRecord.__table__.columns}

    assert "blueprint_id" not in intent_columns
    assert "blueprint_node_id" not in intent_columns
    assert "status" in intent_columns
    assert "payload" in intent_columns
