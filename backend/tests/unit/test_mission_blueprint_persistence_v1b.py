from __future__ import annotations

from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.mission.blueprint import (
    BlueprintDependency,
    BlueprintEvidenceRequirement,
    BlueprintExpansionRule,
    BlueprintNode,
    BlueprintNodeKind,
    BlueprintValidationError,
    MissionBlueprintPersistenceService,
    SqlAlchemyMissionBlueprintRepository,
)
from app.mission.blueprint.migrations import BLUEPRINT_TABLES, DOWNGRADE_SQL, UPGRADE_SQL
from app.models.db import (
    MissionBlueprintDependencyRecord,
    MissionBlueprintNodeRecord,
    MissionBlueprintRecord,
    MissionBlueprintRevisionRecord,
)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def blueprint_flag(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")


def _node(node_id: str, objective: str) -> BlueprintNode:
    return BlueprintNode(
        node_id=node_id,
        objective=objective,
        kind=BlueprintNodeKind.READING,
        owner_capabilities=["knowledge_extraction"],
        evidence_requirements=[
            BlueprintEvidenceRequirement(
                requirement_id=f"evidence_{node_id}",
                evidence_kind="page_read",
                subject=node_id,
            )
        ],
        expansion_rules=[
            BlueprintExpansionRule(
                rule_id=f"expand_{node_id}",
                capability="knowledge_extraction",
                intent_template="read_page",
            )
        ],
    )


def _service(db_session) -> MissionBlueprintPersistenceService:
    return MissionBlueprintPersistenceService(SqlAlchemyMissionBlueprintRepository(db_session))


def _create_blueprint(service: MissionBlueprintPersistenceService, mission_id: str = "mission-blueprint-test"):
    return service.create(
        mission_id=mission_id,
        objective="Research AI browser tools",
        nodes=[
            _node("discover", "Discover source candidates"),
            _node("read", "Read selected source pages"),
        ],
        dependencies=[
            BlueprintDependency(
                dependency_id="dep_discover_read",
                from_node_id="discover",
                to_node_id="read",
            )
        ],
        success_criteria=["table_delivered"],
        reason="initial test blueprint",
    )


def test_repository_crud_round_trip(db_session, blueprint_flag):
    service = _service(db_session)
    blueprint = _create_blueprint(service)

    loaded = service.load(blueprint.mission_id)

    assert loaded is not None
    assert loaded.blueprint_id == blueprint.blueprint_id
    assert loaded.objective == "Research AI browser tools"
    assert [node.node_id for node in loaded.nodes] == ["discover", "read"]
    assert loaded.dependencies[0].to_node_id == "read"


def test_repository_persists_root_revision_nodes_and_dependencies(db_session, blueprint_flag):
    service = _service(db_session)
    blueprint = _create_blueprint(service)

    assert db_session.query(MissionBlueprintRecord).count() == 1
    assert db_session.query(MissionBlueprintRevisionRecord).count() == 1
    assert db_session.query(MissionBlueprintNodeRecord).count() == 2
    assert db_session.query(MissionBlueprintDependencyRecord).count() == 1
    assert db_session.query(MissionBlueprintRecord).first().mission_id == blueprint.mission_id


def test_repository_update_creates_new_revision(db_session, blueprint_flag):
    service = _service(db_session)
    blueprint = _create_blueprint(service)
    updated = replace(
        blueprint,
        revision=2,
        objective="Research AI browser tools and summarize limitations",
    )

    saved = service.save(updated, reason="objective refinement")
    revision_two = service.get_revision(saved.mission_id, 2)
    revisions = service.list_revisions(saved.mission_id)

    assert revision_two is not None
    assert revision_two.objective.endswith("limitations")
    assert [revision["revision"] for revision in revisions] == [1, 2]
    assert revisions[1]["reason"] == "objective refinement"


def test_repository_lists_nodes_for_active_and_revision(db_session, blueprint_flag):
    service = _service(db_session)
    blueprint = _create_blueprint(service)

    active_nodes = service.list_nodes(blueprint.mission_id)
    revision_nodes = service.list_nodes(blueprint.mission_id, revision=1)

    assert [node.node_id for node in active_nodes] == ["discover", "read"]
    assert [node.node_id for node in revision_nodes] == ["discover", "read"]


def test_repository_is_disabled_when_feature_flag_off(db_session, monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "off")
    service = _service(db_session)

    with pytest.raises(BlueprintValidationError, match="disabled"):
        _create_blueprint(service)


def test_migration_metadata_is_additive_and_has_rollback():
    assert set(BLUEPRINT_TABLES) == {
        "mission_blueprints",
        "mission_blueprint_revisions",
        "mission_blueprint_nodes",
        "mission_blueprint_dependencies",
    }
    assert len(UPGRADE_SQL) == 4
    assert len(DOWNGRADE_SQL) == 4
    assert all("CREATE TABLE IF NOT EXISTS" in statement for statement in UPGRADE_SQL)
    assert all(statement.startswith("DROP TABLE IF EXISTS") for statement in DOWNGRADE_SQL)


def test_sqlalchemy_metadata_contains_blueprint_tables(db_session):
    table_names = set(Base.metadata.tables.keys())
    assert set(BLUEPRINT_TABLES).issubset(table_names)


def test_read_only_api_returns_blueprint_nodes_and_revisions(db_session, blueprint_flag):
    service = _service(db_session)
    blueprint = _create_blueprint(service)

    def override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(fastapi_app)
        root = client.get(f"/mission/{blueprint.mission_id}/blueprint")
        nodes = client.get(f"/mission/{blueprint.mission_id}/blueprint/nodes")
        revisions = client.get(f"/mission/{blueprint.mission_id}/blueprint/revisions")
        revision = client.get(f"/mission/{blueprint.mission_id}/blueprint/revision/1")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert root.status_code == 200, root.text
    assert root.json()["blueprint_id"] == blueprint.blueprint_id
    assert nodes.status_code == 200, nodes.text
    assert len(nodes.json()["nodes"]) == 2
    assert revisions.status_code == 200, revisions.text
    assert revisions.json()["revisions"][0]["revision"] == 1
    assert revision.status_code == 200, revision.text
    assert revision.json()["revision"] == 1


def test_read_only_api_disabled_when_flag_off(db_session, monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "off")

    def override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(fastapi_app)
        response = client.get("/mission/anything/blueprint")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "disabled" in response.json()["detail"]


def test_runtime_v1_ledger_schema_is_not_modified_by_blueprint_tables(db_session, blueprint_flag):
    from app.models.db import MissionIntentRecord

    intent_columns = {column.name for column in MissionIntentRecord.__table__.columns}

    assert "blueprint_id" not in intent_columns
    assert "blueprint_node_id" not in intent_columns
    assert "intent_id" in intent_columns
