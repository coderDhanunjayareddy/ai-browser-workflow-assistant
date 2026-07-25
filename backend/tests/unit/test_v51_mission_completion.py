from __future__ import annotations

from app.core.config import settings
from app.knowledge_extraction.engine import KnowledgeExtractionPipeline
from app.mission_completion.engine import MissionCompletionController
from app.mission_completion.models import CompletionDecision
from app.schemas.request import ContentBlock, PageContext
from app.schemas.response import AnalyzeResponse


def _page(text: str = "Example Tool automates browser workflows. Free plan available. Limited support.") -> PageContext:
    return PageContext(
        url="https://example.test/tool",
        title="Example Tool",
        metadata={},
        interactive_elements=[],
        content_blocks=[ContentBlock(selector="#main", text=text, href="https://example.test/tool")],
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

    assert completion.decision == CompletionDecision.RETRY
    assert completion.retry_target == "report"


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
