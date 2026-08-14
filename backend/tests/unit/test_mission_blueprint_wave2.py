from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.mission.blueprint import BlueprintNodeKind
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
        "research_mission",
        "open_search_engine",
        "execute_search",
        "collect_serp_results",
        "rank_results",
        "open_result_1",
        "read_page_1",
        "extract_fields_1",
        "open_result_2",
        "read_page_2",
        "extract_fields_2",
        "open_result_3",
        "read_page_3",
        "extract_fields_3",
        "open_result_4",
        "read_page_4",
        "extract_fields_4",
        "open_result_5",
        "read_page_5",
        "extract_fields_5",
        "validate_coverage",
        "generate_report",
    ]
    assert "top_n:5" in result.blueprint.constraints
    assert "output_table_only" in result.blueprint.constraints
    assert result.blueprint.metadata["mission_classification"]["primary_type"] == "research"
    assert result.blueprint.nodes[1].kind == BlueprintNodeKind.SEARCH_ENGINE_ENTRY
    assert result.blueprint.nodes[1].expansion_template == {"provider": "browser_control", "action": "navigate", "passive": True}


def test_research_search_query_stops_before_result_instructions(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-research-query",
        user_goal=(
            "Open Google Search and search for: best AI browser automation tools 2026. "
            "From the first page of results: 1. Open the top 5 relevant results in new tabs."
        ),
    )

    execute_search = next(node for node in result.blueprint.nodes if node.node_id == "execute_search")
    assert execute_search.metadata["action_payload"]["value"] == (
        "https://www.google.com/search?q=best+AI+browser+automation+tools+2026"
    )


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


def test_navigation_goal_resolves_known_web_app_url(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-whatsapp-navigation",
        user_goal="Open WhatsApp Web and send a hii message to Rahul.",
    )

    reach = next(node for node in result.blueprint.nodes if node.node_id == "reach_target_state")
    assert reach.metadata["action_payload"]["value"] == "https://web.whatsapp.com/"
    assert reach.metadata["action_payload"]["action_type"] == "navigate"


def test_search_result_pricing_comparison_creates_research_blueprint(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-pricing-comparison",
        user_goal=(
            "Open the official websites of 3 AI code assistant products from search results. "
            "Find pricing pages and return a comparison table with source URLs."
        ),
    )

    assert result.mission_type == MissionType.RESEARCH
    assert "open_result_3" in [node.node_id for node in result.blueprint.nodes]
    assert "generate_report" in [node.node_id for node in result.blueprint.nodes]


def test_official_documentation_search_creates_research_blueprint(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-docs-research",
        user_goal=(
            "Search the web for official documentation or product pages about browser automation tools. "
            "Pick 3 different tools and extract supported languages and setup requirements."
        ),
    )

    assert result.mission_type == MissionType.RESEARCH
    assert "collect_serp_results" in [node.node_id for node in result.blueprint.nodes]
    assert "extract_fields_3" in [node.node_id for node in result.blueprint.nodes]


def test_signup_and_public_form_do_not_become_research_blueprints(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    signup = MissionBlueprintBuilder().build(
        mission_id="wave2-signup-policy",
        user_goal=(
            "Open a real SaaS website that offers a free account or free trial, complete the signup flow, "
            "locate one profile field, and return a report."
        ),
    )
    form = MissionBlueprintBuilder().build(
        mission_id="wave2-public-form-policy",
        user_goal="Open a public form with test data, fix validation errors, and submit only if it is a sandbox form.",
    )

    assert signup.mission_type == MissionType.NAVIGATION
    assert form.mission_type == MissionType.NAVIGATION
    assert "fill_form_fields" in [node.node_id for node in signup.blueprint.nodes]
    assert "fill_form_fields" in [node.node_id for node in form.blueprint.nodes]
    assert "validate_form_state" in [node.node_id for node in form.blueprint.nodes]
    assert "Form Workflow" in form.capabilities.capabilities
    signup_policy = next(node for node in signup.blueprint.nodes if node.node_id == "define_form_workflow").metadata["action_payload"]["signup_policy"]
    assert signup_policy["submit_gate"] == "explicit_approval_required"
    assert "payment_or_checkout" in signup_policy["blocked_actions"]
    fill_node = next(node for node in form.blueprint.nodes if node.node_id == "fill_form_fields")
    assert fill_node.metadata["action_payload"]["form_workflow"]["requires_fake_data"] is True
    assert "signup_policy" not in fill_node.metadata["action_payload"]["form_workflow"]
    submit_node = next(node for node in form.blueprint.nodes if node.node_id == "submit_if_policy_allows")
    assert submit_node.metadata["action_payload"]["submit_policy"] == "sandbox_only"


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


def test_file_upload_goal_creates_upload_broker_graph(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-upload",
        user_goal="Open a public upload page, upload a small PDF file, confirm it was accepted, and report the result.",
    )

    node_ids = [node.node_id for node in result.blueprint.nodes]
    assert result.mission_type == MissionType.FILE_PROCESSING
    assert "locate_upload_target" in node_ids
    locate = next(node for node in result.blueprint.nodes if node.node_id == "locate_upload_target")
    assert locate.expansion_template["action"] == "wait"
    assert locate.metadata["action_payload"]["value"] == "500"
    assert "activate_upload_control" in node_ids
    activate = next(node for node in result.blueprint.nodes if node.node_id == "activate_upload_control")
    policy = activate.metadata["action_payload"]["file_upload_broker"]
    assert policy["requires_user_selected_file"] is True
    assert "pdf" in policy["allowed_file_kinds"]
    assert "upload_accepted" in policy["required_evidence"]


def test_natural_language_attachment_goal_uses_upload_broker_and_browser(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-attachment",
        user_goal=(
            "Open WhatsApp Web, find Rahul, and attach the exact local file "
            "Project_Tracker_Status.xlsx. Do not send until approved."
        ),
    )

    node_ids = [node.node_id for node in result.blueprint.nodes]
    assert result.mission_type == MissionType.FILE_PROCESSING
    assert "Browser" in result.capabilities.capabilities
    assert "open_upload_destination" in node_ids
    assert "locate_upload_target" in node_ids
    assert "activate_upload_control" in node_ids
    destination = next(node for node in result.blueprint.nodes if node.node_id == "open_upload_destination")
    assert destination.expansion_template["action"] == "click"
    assert destination.metadata["action_payload"]["value"] == "Rahul"


def test_dependency_graph_is_sequential_acyclic_and_critical(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-deps",
        user_goal="Research best browser automation tools and create a report.",
    )

    assert result.dependencies.sequential_dependencies
    assert result.dependencies.critical_path
    assert result.dependencies.evidence_dependencies
    assert len(result.blueprint.dependencies) >= len(result.blueprint.nodes) - 1


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


def test_optional_clarification_does_not_block_research_graph(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-optional-clarify",
        user_goal="Research the best AI browser automation tools and create a report.",
    )

    assert result.blueprint.nodes[0].node_id == "research_mission"
    assert all(dependency.kind.value != "clarification" for dependency in result.blueprint.dependencies)
    assert any(
        item["clarification_id"] == "clarify_ranking_or_relevance_policy" and item["required"] is False
        for item in result.blueprint.metadata["clarification_requirements"]
    )


def test_research_benchmark_generates_executable_parallel_graph(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="wave2-benchmark",
        user_goal=(
            "Open Google, search best AI browser automation tools 2026, open top 5, "
            "read each page, extract fields, and report."
        ),
    )
    nodes = {node.node_id: node for node in result.blueprint.nodes}
    edges = {(dependency.from_node_id, dependency.to_node_id) for dependency in result.blueprint.dependencies}

    assert "runtime_state" not in {node.expansion_template["provider"] for node in result.blueprint.nodes}
    assert nodes["execute_search"].expansion_template["provider"] == "browser_control"
    assert nodes["collect_serp_results"].expansion_template["action"] == "collect_search_results"
    assert nodes["open_result_1"].parallel_policy["parallelizable"] is True
    assert nodes["read_page_5"].parallel_policy["group"] == "result_pages"
    assert ("rank_results", "open_result_1") in edges
    assert ("rank_results", "open_result_5") in edges
    assert ("extract_fields_1", "validate_coverage") in edges
    assert ("extract_fields_5", "validate_coverage") in edges
    assert ("validate_coverage", "generate_report") in edges


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


def test_wave2_keeps_runtime_v1_ledger_lifecycle_contract():
    from app.models.db import MissionIntentRecord

    intent_columns = {column.name for column in MissionIntentRecord.__table__.columns}

    assert "blueprint_id" in intent_columns
    assert "blueprint_node_id" in intent_columns
    assert "blueprint_revision" in intent_columns
    assert "blueprint_readiness" not in intent_columns
    assert "status" in intent_columns
    assert "payload" in intent_columns
