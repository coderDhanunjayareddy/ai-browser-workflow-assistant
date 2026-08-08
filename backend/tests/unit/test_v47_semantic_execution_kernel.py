from __future__ import annotations

from app.core.config import settings
from app.schemas.request import ContentBlock, InteractiveElement, PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.runtime_state_manager.entity_binding import bind_runtime_resource, list_entities, register_entity
from app.runtime_state_manager.entity_pipeline_trace import entity_pipeline_replay, entity_pipeline_telemetry
from app.semantic_execution_kernel.engine import SemanticExecutionKernel
from app.semantic_execution_kernel.mission_state import build_mission_state


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
    assert settings.__class__.model_fields["v47_semantic_execution_kernel"].default == "shadow"
    assert settings.__class__.model_fields["v493_entity_pipeline_trace"].default == "shadow"


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
    assert all(entity.trace_id for entity in snapshot.entities)
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
    assert "ENTITY_PIPELINE_FAILURE stage=SemanticKernel" in result.replan.reason
    assert "entity lookup failed" in result.replan.reason


def test_entity_pipeline_replay_groups_contract_boundaries(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "shadow")
    monkeypatch.setattr(settings, "v493_entity_pipeline_trace", "shadow")
    engine = SemanticExecutionKernel()
    session_id = "kernel-pipeline-replay"
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task="Open a result. Read the page. Return final answer.",
        page_context=_page(),
        prior_steps=[],
    )
    engine.enrich_context({"active_goal": "x"}, snapshot)

    telemetry = entity_pipeline_telemetry(session_id)
    replay = entity_pipeline_replay(session_id)

    assert telemetry["entities_registered"] >= 1
    assert telemetry["entities_sent_to_planner"] >= 1
    assert telemetry["entities_received_by_kernel"] >= 1
    assert replay["registered_entities"]
    assert replay["planner_entities"]
    assert replay["kernel_entities"]
    assert replay["timeline"]


def test_active_entity_pipeline_reports_exact_stage_for_missing_planner_url(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    monkeypatch.setattr(settings, "v493_entity_pipeline_trace", "active")
    engine = SemanticExecutionKernel()
    session_id = "kernel-url-missing-contract"
    response = _response("open_new_tab", value="https://missing.example.test/not-registered")

    result = engine.postprocess_response(
        result=response,
        session_id=session_id,
        task="Open the external result. Return final answer.",
        page_context=_page(),
        prior_steps=[],
    )

    assert result.outcome_kind == "replan"
    assert result.replan is not None
    assert "ENTITY_PIPELINE_FAILURE stage=SEMANTIC_KERNEL" in result.replan.reason
    assert not [
        entity for entity in list_entities(session_id)
        if entity.source_layer == "semantic_execution_kernel" and entity.entity_type == "url_candidate"
    ]


def test_search_navigation_clears_stale_entity_lookup_failure(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    monkeypatch.setattr(settings, "v493_entity_pipeline_trace", "active")
    engine = SemanticExecutionKernel()
    session_id = "kernel-search-clears-stale-entity-failure"

    failed = engine.postprocess_response(
        result=_response("open_new_tab", value="https://missing.example.test/not-registered"),
        session_id=session_id,
        task="Search the web and open relevant result pages.",
        page_context=_page(),
        prior_steps=[],
    )
    assert failed.outcome_kind == "replan"

    recovered = engine.postprocess_response(
        result=_response("navigate", value="https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026"),
        session_id=session_id,
        task="Search the web and open relevant result pages.",
        page_context=_page(),
        prior_steps=[],
    )

    assert recovered.outcome_kind == "act"
    assert recovered.suggested_actions[0].action_type == "navigate"
    assert recovered.suggested_actions[0].value == "https://duckduckgo.com/?q=best+AI+browser+automation+tools+2026"
    assert recovered.replan is None


def test_active_kernel_accepts_open_url_when_visible_page_evidence_contains_it(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    monkeypatch.setattr(settings, "v493_entity_pipeline_trace", "active")
    engine = SemanticExecutionKernel()
    session_id = "kernel-page-evidenced-url"
    url = "https://evidenced.example/result"
    page = PageContext(
        url="https://www.bing.com/search?q=browser",
        title="Bing Search",
        metadata={},
        interactive_elements=[],
        content_blocks=[
            ContentBlock(
                selector="#result-text",
                text=f"Evidenced Result {url} is visible in the current search results.",
                href=None,
            )
        ],
        headings=["Search results"],
        selected_text="",
        visible_text=f"Evidenced Result {url} is visible in the current search results.",
        images=[],
    )

    result = engine.postprocess_response(
        result=_response("open_new_tab", value=url),
        session_id=session_id,
        task="Open the external result. Return final answer.",
        page_context=page,
        prior_steps=[],
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].value == url
    assert [
        entity for entity in list_entities(session_id)
        if entity.source_layer == "page_evidence" and entity.canonical_url == url
    ]


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


def test_opened_browser_actions_are_successful_and_do_not_block_read_phase(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    task = """
    Open Google Search and search for: best AI browser automation tools 2026.
    From the first page of results:
    1. Open the top 5 relevant results in new tabs.
    2. Read each page.
    3. Extract Tool, Purpose, Pricing, Limitation, URL.
    4. Produce a comparison table.
    """
    prior = [
        PriorStep(
            action_type="open_new_tab",
            description=f"Open phase entity #{index}: Tool {index}",
            target_selector="",
            value=f"https://tool{index}.example/",
            execution_result=f"Opened new tab: https://tool{index}.example/",
            page_url=f"https://tool{index}.example/",
            page_title=f"Tool {index}",
        )
        for index in range(1, 6)
    ]

    mission_state = build_mission_state(task, prior)

    assert mission_state.blocked is False
    assert mission_state.goals[0].status == "completed"
    assert mission_state.goals[0].retries == 0
    assert mission_state.current_goal_id == "goal_2"

    result = SemanticExecutionKernel().postprocess_response(
        result=_response("focus_existing_tab", value="url:https://tool1.example/"),
        session_id="kernel-opened-success-read",
        task=task,
        page_context=_page(),
        prior_steps=prior,
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "focus_existing_tab"


def test_focus_tab_grounding_translates_logical_tab_to_browser_url_reference(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    session_id = "kernel-logical-tab-boundary"
    logical_tab_id = "logical_tab_cd9c0daa61"
    register_entity(
        session_id,
        entity_type="result",
        title="Pickaxe",
        canonical_url="https://pickaxe.co/post/top-ai-browsers-extensions",
        source_layer="test",
    )
    entity = list_entities(session_id)[0]
    bind_runtime_resource(
        session_id,
        entity_id=entity.entity_id,
        runtime_resource_id=logical_tab_id,
    )

    result = SemanticExecutionKernel().postprocess_response(
        result=_response("focus_existing_tab", value=logical_tab_id),
        session_id=session_id,
        task="Read the opened Pickaxe tab.",
        page_context=_page(),
        prior_steps=[],
    )

    assert result.outcome_kind == "act"
    action = result.suggested_actions[0]
    assert action.action_type == "focus_existing_tab"
    assert action.value == "url:https://pickaxe.co/post/top-ai-browsers-extensions"
    assert "logical_tab_" not in (action.value or "")


def test_open_entity_reference_grounds_to_registered_url(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    session_id = "kernel-entity-reference-open"
    entity = register_entity(
        session_id,
        entity_type="search_result",
        title="Awesome Agents",
        canonical_url="https://awesomeagents.ai/",
        source_layer="browser_intelligence",
    )

    result = SemanticExecutionKernel().postprocess_response(
        result=_response("open_new_tab", value=f"entity:{entity.entity_id}"),
        session_id=session_id,
        task="Open the top collected source.",
        page_context=_page(),
        prior_steps=[],
    )

    assert result.outcome_kind == "act"
    action = result.suggested_actions[0]
    assert action.action_type == "open_new_tab"
    assert action.value == "https://awesomeagents.ai"


def test_focus_tab_grounding_rejects_unresolved_logical_tab_before_browser_boundary(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    result = SemanticExecutionKernel().postprocess_response(
        result=_response("focus_existing_tab", value="logical_tab_missing"),
        session_id="kernel-logical-tab-missing",
        task="Read the opened tab.",
        page_context=_page(),
        prior_steps=[],
    )

    assert result.outcome_kind == "replan"
    assert result.suggested_actions == []
    assert result.replan is not None
    assert "logical tab reference unresolved" in result.replan.reason
