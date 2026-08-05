from __future__ import annotations

from dataclasses import replace

from app.core.config import settings
from app.knowledge_extraction.engine import KnowledgeExtractionPipeline
from app.mission.intelligence.blueprint_builder import MissionBlueprintBuilder
from app.mission.intelligence.mission_plan import create_mission_plan
from app.mission_completion.engine import MissionCompletionController
from app.mission_completion.criteria import evaluate_success_criteria
from app.mission_completion.models import CompletionDecision, CriterionKind, ObjectiveType
from app.schemas.request import ContentBlock, PageContext
from app.schemas.response import AnalyzeResponse, SuggestedAction


def _page(
    text: str = "Example Tool automates browser workflows. Free plan available. Limited support.",
    *,
    url: str = "https://example.test/tool",
) -> PageContext:
    return PageContext(
        url=url,
        title="Example Tool",
        metadata={},
        interactive_elements=[],
        content_blocks=[ContentBlock(selector="#main", text=text, href=url)],
        headings=["Example Tool"],
        selected_text="",
        visible_text=text,
        images=[],
    )


def _newtab_page() -> PageContext:
    text = "This is a blank browser tab or restricted browser settings page. No webpage is loaded yet. Use the navigate action to open a website."
    return PageContext(
        url="chrome://newtab/",
        title="New Tab",
        metadata={},
        interactive_elements=[],
        content_blocks=[ContentBlock(selector="#main", text=text, href="chrome://newtab/")],
        headings=["New Tab"],
        selected_text="",
        visible_text=text,
        images=[],
    )


def _complete_snapshot():
    pipeline = KnowledgeExtractionPipeline()
    return pipeline.observe(
        session_id="v51-complete",
        task="Extract Tool, Purpose, Pricing, Limitation, URL and return a table.",
        page_context=_page(),
        current_phase="SYNTHESIZE",
    )


def test_v51_flag_defaults_to_shadow():
    assert settings.__class__.model_fields["v51_mission_completion_controller"].default == "shadow"


def test_shadow_mode_records_completion_decision_without_replacing_planner(monkeypatch):
    monkeypatch.setattr(settings, "v51_mission_completion_controller", "shadow")
    controller = MissionCompletionController()
    planner = AnalyzeResponse(
        session_id="v51-shadow",
        analysis="Continue opening pages.",
        outcome_kind="wait",
        suggested_actions=[],
    )

    snapshot = controller.observe(
        session_id="v51-shadow",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        knowledge_snapshot=_complete_snapshot(),
        planner_response=planner,
    )
    result = controller.postprocess_response(planner, snapshot)

    assert snapshot.decision == CompletionDecision.COMPLETE
    assert snapshot.mission_plan.success_criteria
    assert all(evaluation.satisfied for evaluation in snapshot.evidence.criteria_evaluations)
    assert result.outcome_kind == "wait"


def test_active_mode_returns_completion_response_before_planner(monkeypatch):
    monkeypatch.setattr(settings, "v51_mission_completion_controller", "active")
    controller = MissionCompletionController()

    snapshot = controller.observe(
        session_id="v51-active",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        knowledge_snapshot=_complete_snapshot(),
    )
    result = controller.completion_response("v51-active", snapshot)

    assert controller.should_terminate_before_planner(snapshot) is True
    assert result.outcome_kind == "report"
    assert result.suggested_actions == []
    assert result.sgv_verified is True
    assert result.goal_convergence is True
    assert result.backend_authoritative_report is True
    assert "| tool | purpose | pricing | limitation | url |" in result.report.answer


def test_active_mode_replaces_repeated_wait_after_completion(monkeypatch):
    monkeypatch.setattr(settings, "v51_mission_completion_controller", "active")
    controller = MissionCompletionController()
    planner = AnalyzeResponse(
        session_id="v51-post",
        analysis="Wait for verification.",
        outcome_kind="wait",
        suggested_actions=[],
    )

    snapshot = controller.observe(
        session_id="v51-post",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        knowledge_snapshot=_complete_snapshot(),
        planner_response=planner,
    )
    result = controller.postprocess_response(planner, snapshot)

    assert result.outcome_kind == "report"
    assert result.suggested_actions == []


def test_missing_report_records_retry_target(monkeypatch):
    monkeypatch.setattr(settings, "v51_mission_completion_controller", "shadow")
    monkeypatch.setattr(settings, "v50_report_engine", "off")
    pipeline = KnowledgeExtractionPipeline()
    snapshot = pipeline.observe(
        session_id="v51-retry",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_page(),
        current_phase="EXTRACT",
    )

    completion = MissionCompletionController().observe(
        session_id="v51-retry",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        knowledge_snapshot=snapshot,
    )

    assert completion.decision == CompletionDecision.INCOMPLETE
    assert completion.retry_target == "report"


def test_active_mode_converts_act_wait_retry_to_backend_replan(monkeypatch):
    monkeypatch.setattr(settings, "v51_mission_completion_controller", "active")
    monkeypatch.setattr(settings, "v50_report_engine", "off")
    pipeline = KnowledgeExtractionPipeline()
    knowledge = pipeline.observe(
        session_id="v51-act-wait-retry",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_page(),
        current_phase="SYNTHESIZE",
    )
    planner_wait = AnalyzeResponse(
        session_id="v51-act-wait-retry",
        analysis="Wait for extraction to finish.",
        outcome_kind="act",
        suggested_actions=[
            SuggestedAction(
                action_id="wait",
                action_type="wait",  # type: ignore[arg-type]
                target_selector="window",
                value="1000",
                description="Wait",
                reasoning="Planner wants browser wait.",
                confidence=0.7,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )

    completion = MissionCompletionController().observe(
        session_id="v51-act-wait-retry",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        knowledge_snapshot=knowledge,
        planner_response=planner_wait,
    )
    result = MissionCompletionController().postprocess_response(planner_wait, completion)

    assert completion.decision == CompletionDecision.INCOMPLETE
    assert result.outcome_kind == "replan"
    assert result.suggested_actions == []
    assert result.replan.reason == completion.reason


def test_restricted_blank_tab_never_completes_mission(monkeypatch):
    monkeypatch.setattr(settings, "v51_mission_completion_controller", "active")
    pipeline = KnowledgeExtractionPipeline()
    snapshot = pipeline.observe(
        session_id="v51-newtab",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_newtab_page(),
        current_phase="READ",
    )

    completion = MissionCompletionController().observe(
        session_id="v51-newtab",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        knowledge_snapshot=snapshot,
    )

    assert snapshot.report_artifact is None
    assert completion.decision != CompletionDecision.COMPLETE
    assert completion.decision != CompletionDecision.PARTIAL_SUCCESS
    assert completion.workflow_result is None


def test_mission_plan_supports_generalized_workflow_criteria():
    examples = [
        ("Research best browser automation tools and produce a report", ObjectiveType.RESEARCH, CriterionKind.REPORT_DELIVERED),
        ("Sign up for a SaaS account", ObjectiveType.ACCOUNT_CREATION, CriterionKind.SUBMISSION_CONFIRMED),
        ("Buy the selected product after approval", ObjectiveType.SHOPPING, CriterionKind.APPROVAL_OBTAINED),
        ("Apply for this job using my resume", ObjectiveType.JOB_APPLICATION, CriterionKind.SUBMISSION_CONFIRMED),
        ("Upload the required file", ObjectiveType.UPLOAD, CriterionKind.FILE_UPLOADED),
        ("Download the invoice PDF", ObjectiveType.DOWNLOAD, CriterionKind.FILE_DOWNLOADED),
        ("Extract API documentation sections", ObjectiveType.DOCUMENTATION_EXTRACTION, CriterionKind.FIELD_EXTRACTED),
        ("Wait for external confirmation email", ObjectiveType.ASYNC_WORKFLOW, CriterionKind.EXTERNAL_CONFIRMATION_RECEIVED),
        ("Open the analytics dashboard", ObjectiveType.DASHBOARD, CriterionKind.RUNTIME_BINDING_EXISTS),
    ]

    for objective, objective_type, expected_kind in examples:
        plan = create_mission_plan(mission_id=f"plan-{objective_type.value}", objective=objective)
        kinds = {criterion.kind for criterion in plan.success_criteria}

        assert plan.objective_type == objective_type
        assert expected_kind in kinds
        assert plan.termination_rules


def test_directory_collection_blueprint_includes_collection_policy_nodes(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")

    result = MissionBlueprintBuilder().build(
        mission_id="directory-blueprint",
        user_goal="Collect 50 entries from a multi-page directory.",
    )
    node_ids = [node.node_id for node in result.blueprint.nodes]
    collect_node = next(node for node in result.blueprint.nodes if node.node_id == "collect_page_items")
    pagination_node = next(node for node in result.blueprint.nodes if node.node_id == "advance_pagination")

    assert "collect_page_items" in node_ids
    assert "advance_pagination" in node_ids
    assert collect_node.repeat_policy["mode"] == "until_collection_policy_stop"
    assert collect_node.metadata["action_payload"]["policy"] == "collection_policy.v1"
    assert "no_new_items" in pagination_node.metadata["action_payload"]["stop_conditions"]


def test_explicit_url_collection_blueprint_navigates_directly_without_search(monkeypatch):
    monkeypatch.setattr(settings, "mission_blueprint_v1", "shadow")
    prompt = """Open this public test directory page: https://quotes.toscrape.com/page/1/

Collect 20 entries from this multi-page directory.

Extract:
- quote text
- author
- tags
- source URL

Return a clean table only."""

    result = MissionBlueprintBuilder().build(
        mission_id="quotes-direct-blueprint",
        user_goal=prompt,
    )
    node_ids = [node.node_id for node in result.blueprint.nodes]
    locate_source = next(node for node in result.blueprint.nodes if node.node_id == "locate_source")

    assert "open_search_engine" not in node_ids
    assert "execute_search" not in node_ids
    assert "collect_page_items" in node_ids
    assert locate_source.metadata["action_payload"]["value"] == "https://quotes.toscrape.com/page/1/"


def test_criteria_evaluation_uses_provider_evidence_not_report_existence_only(monkeypatch):
    monkeypatch.setattr(settings, "v51_mission_completion_controller", "shadow")
    pipeline = KnowledgeExtractionPipeline()
    knowledge = pipeline.observe(
        session_id="v51-criteria",
        task="Extract Tool, Purpose, Pricing, Limitation, URL.",
        page_context=_page(),
        current_phase="SYNTHESIZE",
    )
    report_without_records = replace(knowledge, extraction_records=[])
    plan = create_mission_plan(
        mission_id="v51-criteria",
        objective="Extract Tool, Purpose, Pricing, Limitation, URL.",
    )

    evaluations = evaluate_success_criteria(mission_plan=plan, knowledge_snapshot=report_without_records)
    by_kind = {evaluation.kind: evaluation for evaluation in evaluations}

    assert by_kind[CriterionKind.REPORT_DELIVERED].satisfied is True
    assert by_kind[CriterionKind.FIELD_EXTRACTED].satisfied is False
    assert by_kind[CriterionKind.FIELD_EXTRACTED].missing_evidence


def test_research_source_count_requires_distinct_source_pages(monkeypatch):
    monkeypatch.setattr(settings, "v51_mission_completion_controller", "shadow")
    pipeline = KnowledgeExtractionPipeline()
    task = (
        "Search for: best AI browser automation tools 2026. "
        "Open the top 2 relevant results. "
        "Create a clean comparison table with columns: Tool, Purpose, Pricing, Limitation, URL."
    )
    knowledge = pipeline.observe(
        session_id="v51-source-coverage",
        task=task,
        page_context=_page(url="https://example.test/tool?utm_source=test"),
        current_phase="SYNTHESIZE",
    )
    duplicated_source = replace(
        knowledge,
        read_artifacts=[knowledge.read_artifacts[0], knowledge.read_artifacts[0]],
        extraction_records=[knowledge.extraction_records[0], knowledge.extraction_records[0]],
    )
    plan = create_mission_plan(mission_id="v51-source-coverage", objective=task)

    evaluations = evaluate_success_criteria(mission_plan=plan, knowledge_snapshot=duplicated_source)
    by_kind = {evaluation.kind: evaluation for evaluation in evaluations}
    completion = MissionCompletionController().observe(
        session_id="v51-source-coverage",
        task=task,
        knowledge_snapshot=duplicated_source,
    )

    assert by_kind[CriterionKind.PAGE_READ].satisfied is False
    assert by_kind[CriterionKind.FIELD_EXTRACTED].satisfied is False
    assert by_kind[CriterionKind.ARTIFACT_VALIDATED].satisfied is False
    assert completion.evidence.source_coverage is not None
    assert completion.evidence.source_coverage.required_count == 2
    assert completion.evidence.source_coverage.distinct_count == 1
