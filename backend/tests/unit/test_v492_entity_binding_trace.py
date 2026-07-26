from __future__ import annotations

from app.browser_intelligence import build_browser_intelligence
from app.core.config import settings
from app.runtime_state_manager.entity_binding import entity_binding_trace, registry_identity, resolve_entity
from app.runtime_state_manager.registry import BrowserRuntimeRegistry
from app.schemas.request import ContentBlock, InteractiveElement, PageContext
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.services.ai_service import _postprocess_planner_response
from app.semantic_execution_kernel.engine import SemanticExecutionKernel


def _serp_page() -> PageContext:
    return PageContext(
        url="https://www.search.test/?q=browser+automation",
        title="Search results",
        metadata={},
        interactive_elements=[
            InteractiveElement(
                type="a",
                selector='a[href="https://pickaxe.co"]',
                text="Pickaxe",
                href="https://pickaxe.co",
                visible=True,
            )
        ],
        content_blocks=[
            ContentBlock(
                selector='a[href="https://pickaxe.co"]',
                text="Pickaxe AI browser automation platform.",
                href="https://pickaxe.co",
            )
        ],
        headings=["Search results"],
        selected_text="",
        visible_text="Pickaxe AI browser automation platform.",
        images=[],
    )


def _google_serp_with_result() -> PageContext:
    return PageContext(
        url="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
        title="best AI browser automation tools 2026 - Google Search",
        metadata={},
        interactive_elements=[
            InteractiveElement(
                type="a",
                selector='a[href="https://pickaxe.co"]',
                text="Top 25 AI Browsers & Extensions in 2026",
                href="https://pickaxe.co",
                visible=True,
            )
        ],
        content_blocks=[
            ContentBlock(
                selector='a[href="https://pickaxe.co"]',
                text="Top 25 AI Browsers & Extensions in 2026 Pickaxe.co",
                href="https://pickaxe.co",
            )
        ],
        headings=["Search results"],
        selected_text="",
        visible_text="Top 25 AI Browsers & Extensions in 2026 Pickaxe.co",
        images=[],
    )


def _google_serp_without_result_dom() -> PageContext:
    return PageContext(
        url="https://www.google.com/search?q=best+AI+browser+automation+tools+2026",
        title="best AI browser automation tools 2026 - Google Search",
        metadata={},
        interactive_elements=[
            InteractiveElement(type="textarea", selector="#APjFqb", text="best AI browser automation tools 2026", visible=True),
            InteractiveElement(type="button", selector='button[aria-label="Search"]', text="", visible=True),
        ],
        content_blocks=[],
        headings=["Search results"],
        selected_text="",
        visible_text="AI Mode All Short videos",
        images=[],
    )


def _open_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="trace-mission",
        analysis="Open registered result.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="open-pickaxe",
                action_type="open_new_tab",  # type: ignore[arg-type]
                target_selector="",
                value="https://pickaxe.co",
                description="Open Pickaxe",
                reasoning="Use explicit URL.",
                confidence=0.9,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )


def test_trace_records_registration_lookup_and_grounding(monkeypatch):
    monkeypatch.setattr(settings, "v45_browser_intelligence", "active")
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    before = registry_identity("trace-mission")
    build_browser_intelligence(_serp_page(), scope_id="trace-mission")
    after_bi = registry_identity("trace-mission")

    assert before["registry_instance"] == after_bi["registry_instance"]
    assert resolve_entity("trace-mission", canonical_url="https://pickaxe.co") is not None

    result = SemanticExecutionKernel().postprocess_response(
        result=_open_response(),
        session_id="trace-mission",
        task="Open the top result.",
        page_context=_serp_page(),
        prior_steps=[],
    )
    after_kernel = registry_identity("trace-mission")
    trace = entity_binding_trace("trace-mission", limit=80)
    events = [(item["event"], item["outcome"], item["resolved_by"]) for item in trace]

    assert before["registry_instance"] == after_kernel["registry_instance"]
    assert result.outcome_kind == "act", result.replan.reason if result.replan else result.analysis
    assert ("REGISTER_ENTITY", "success", None) in events
    assert ("LOOKUP_ENTITY_ID", "MISS", None) in events
    assert ("LOOKUP_ARTIFACT_ID", "MISS", None) in events
    assert ("LOOKUP_CANONICAL_URL", "HIT", "canonical_url") in events
    assert resolve_entity("trace-mission", canonical_url="https://pickaxe.co").state == "GROUNDED"


def test_runtime_binding_trace_after_tab_sync(monkeypatch):
    monkeypatch.setattr(settings, "v49_runtime_state_manager", "active")
    build_browser_intelligence(_serp_page(), scope_id="trace-runtime")
    registry = BrowserRuntimeRegistry()

    registry.synchronize(
        "trace-runtime",
        PageContext(
            url="https://pickaxe.co",
            title="Pickaxe",
            metadata={},
            interactive_elements=[],
            content_blocks=[],
            headings=[],
            selected_text="",
            visible_text="",
            images=[],
        ),
        [],
    )

    trace = entity_binding_trace("trace-runtime", limit=80)
    assert any(item["event"] == "RUNTIME_BINDING" and item["outcome"] == "success" for item in trace)
    entity = resolve_entity("trace-runtime", canonical_url="https://pickaxe.co")
    assert entity is not None
    assert entity.runtime_resource_id is not None


def test_ai_service_repaired_open_url_is_registered_before_kernel(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    task = "Open Google Search and search for: `best AI browser automation tools 2026`. Open the top 5 relevant results."
    planner = AnalyzeResponse(
        session_id="trace-repair",
        analysis="Open first result.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="open_result_1",
                action_type="open_new_tab",  # type: ignore[arg-type]
                target_selector="#rso > div:nth-of-type(6)",
                value="https://pickaxe.co",
                description="Open the first search result in a new tab.",
                reasoning="Open result.",
                confidence=1.0,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )

    repaired = _postprocess_planner_response(
        planner,
        page_context=_google_serp_with_result(),
        task=task,
        prior_steps=[],
    )
    entity = resolve_entity("trace-repair", canonical_url="https://pickaxe.co")

    assert repaired.suggested_actions[0].action_type == "open_new_tab"
    assert repaired.suggested_actions[0].value == "https://pickaxe.co"
    assert entity is not None
    assert entity.source_layer == "browser_intelligence_repair"

    result = SemanticExecutionKernel().postprocess_response(
        result=repaired,
        session_id="trace-repair",
        task=task,
        page_context=_google_serp_without_result_dom(),
        prior_steps=[],
    )

    assert result.outcome_kind == "act", result.replan.reason if result.replan else result.analysis
    assert result.suggested_actions[0].value == "https://pickaxe.co"


def test_kernel_registers_safe_open_new_tab_url_when_binding_missing(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    response = _open_response()
    response.session_id = "trace-kernel-url-fallback"

    result = SemanticExecutionKernel().postprocess_response(
        result=response,
        session_id="trace-kernel-url-fallback",
        task="Open the explicit URL.",
        page_context=_google_serp_without_result_dom(),
        prior_steps=[],
    )

    entity = resolve_entity("trace-kernel-url-fallback", canonical_url="https://pickaxe.co")
    assert result.outcome_kind == "act", result.replan.reason if result.replan else result.analysis
    assert entity is not None
    assert entity.source_layer == "semantic_execution_kernel"
