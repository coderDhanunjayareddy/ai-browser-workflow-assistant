from __future__ import annotations

from app.core.config import settings
from app.feature_flags import get_flag_state
from app.schemas.request import ContentBlock, InteractiveElement, PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.semantic_execution_kernel.engine import SemanticExecutionKernel


def _page() -> PageContext:
    return PageContext(
        url="https://example.test/list",
        title="Example Directory",
        metadata={},
        interactive_elements=[
            InteractiveElement(
                type="a",
                selector="#result-1",
                text="Example Result",
                href="https://example.test/result/1",
                visible=True,
            ),
            InteractiveElement(
                type="button",
                selector="#save",
                text="Save",
                visible=True,
            ),
        ],
        content_blocks=[
            ContentBlock(
                selector="#card-1",
                text="Example Result has a pricing page and documentation.",
                href="https://example.test/result/1",
            )
        ],
        headings=["Example Directory"],
        selected_text="",
        visible_text="Example Result has a pricing page and documentation.",
        images=[],
    )


def _response(action_type: str, *, value: str | None = None, selector: str = "") -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="kernel-session",
        analysis="Open the relevant entity.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="candidate",
                action_type=action_type,  # type: ignore[arg-type]
                target_selector=selector,
                value=value,
                description="Open Example Result",
                reasoning="Planner proposal.",
                confidence=0.8,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )


def test_semantic_kernel_feature_flag_defaults_to_shadow():
    assert get_flag_state("V47_SEMANTIC_EXECUTION_KERNEL").value == "shadow"


def test_shadow_kernel_builds_entities_without_context_enrichment(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "shadow")
    engine = SemanticExecutionKernel()

    snapshot = engine.build_snapshot(
        session_id="kernel-shadow",
        task="Open a result. Read the page. Return final answer.",
        page_context=_page(),
        prior_steps=[],
    )

    assert snapshot is not None
    assert any(entity.url == "https://example.test/result/1" for entity in snapshot.entities)
    assert engine.enrich_context({"active_goal": "x"}, snapshot) == {"active_goal": "x"}


def test_active_kernel_enriches_context_with_legal_semantic_actions(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    engine = SemanticExecutionKernel()
    snapshot = engine.build_snapshot(
        session_id="kernel-active",
        task="Open a result. Read the page. Return final answer.",
        page_context=_page(),
        prior_steps=[],
    )

    enriched = engine.enrich_context({"active_goal": "x"}, snapshot)

    assert "semantic_execution_kernel" in enriched
    assert "legal_semantic_actions" in enriched
    assert any(action["action"] == "OPEN_ENTITY" for action in enriched["legal_semantic_actions"])


def test_active_kernel_grounds_registered_entity_url(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    engine = SemanticExecutionKernel()
    response = _response("open_new_tab", value="https://example.test/result/1")

    grounded = engine.postprocess_response(
        result=response,
        session_id="kernel-ground",
        task="Open a result. Read the page. Return final answer.",
        page_context=_page(),
        prior_steps=[],
    )

    assert grounded.outcome_kind == "act"
    assert grounded.suggested_actions[0].action_type == "open_new_tab"
    assert grounded.suggested_actions[0].value == "https://example.test/result/1"
    assert "Semantic Execution Kernel grounded" in grounded.suggested_actions[0].reasoning


def test_active_kernel_rejects_unregistered_entity_before_browser_execution(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    engine = SemanticExecutionKernel()
    response = _response("click", selector="#invented")

    result = engine.postprocess_response(
        result=response,
        session_id="kernel-reject",
        task="Click the visible save button. Return final answer.",
        page_context=_page(),
        prior_steps=[],
    )

    assert result.outcome_kind == "replan"
    assert result.suggested_actions == []
    assert result.replan is not None
    assert "entity_missing" in result.replan.reason


def test_kernel_loop_prevention_rejects_duplicate_proposal(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    engine = SemanticExecutionKernel()
    response = _response("open_new_tab", value="https://example.test/result/1")
    prior = [
        PriorStep(
            action_type="open_new_tab",
            description="Open Example Result",
            target_selector="",
            value="https://example.test/result/1",
            execution_result="success",
            page_url="https://example.test/list",
            page_title="Example Directory",
        ),
        PriorStep(
            action_type="open_new_tab",
            description="Open Example Result",
            target_selector="",
            value="https://example.test/result/1",
            execution_result="success",
            page_url="https://example.test/list",
            page_title="Example Directory",
        ),
    ]

    result = engine.postprocess_response(
        result=response,
        session_id="kernel-loop",
        task="Open a result. Read the page. Return final answer.",
        page_context=_page(),
        prior_steps=prior,
    )

    assert result.outcome_kind == "replan"
    assert result.replan is not None
    assert "loop_detected" in result.replan.reason
