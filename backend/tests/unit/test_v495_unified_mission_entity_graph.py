from __future__ import annotations

from app.core.config import settings
from app.runtime_state_manager.entity_binding import list_entities, register_entity, resolve_entity
from app.schemas.request import InteractiveElement, PageContext
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.semantic_execution_kernel.engine import SemanticExecutionKernel


def _crowded_page(count: int = 150) -> PageContext:
    return PageContext(
        url="https://search.example.test/results",
        title="Crowded results",
        metadata={},
        interactive_elements=[
            InteractiveElement(
                type="a",
                selector=f"#legacy-{index}",
                text=f"Legacy result {index}",
                href=f"https://legacy.example.test/{index}",
                visible=True,
            )
            for index in range(count)
        ],
        content_blocks=[],
        headings=["Crowded results"],
        selected_text="",
        visible_text="Crowded results",
        images=[],
    )


def _open_pickaxe(session_id: str) -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id=session_id,
        analysis="Open the registered result URL.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="open_registered_result",
                action_type="open_new_tab",  # type: ignore[arg-type]
                target_selector="",
                value="https://pickaxe.co",
                description="Open Pickaxe",
                reasoning="Planner selected an observed Browser Intelligence entity.",
                confidence=0.9,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )


def test_kernel_snapshot_uses_authoritative_mission_graph_without_entity_cap(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    session_id = "v495-authoritative-graph"
    runtime_entity = register_entity(
        session_id,
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Pickaxe",
        canonical_url="https://pickaxe.co",
        artifact_id="bi:search_result:v495:1",
        selector_ids=["#rso > div:nth-of-type(8)"],
        confidence=0.92,
        source_page="https://search.example.test/results",
    )

    engine = SemanticExecutionKernel()
    snapshot = engine.build_snapshot(
        session_id=session_id,
        task="Open the top relevant result.",
        page_context=_crowded_page(),
        prior_steps=[],
    )

    assert snapshot is not None
    graph_ids = {entity.entity_id for entity in list_entities(session_id)}
    kernel_ids = {entity.id for entity in snapshot.entities}
    assert runtime_entity.entity_id in graph_ids
    assert runtime_entity.entity_id in kernel_ids
    assert graph_ids <= kernel_ids
    assert len(snapshot.entities) > 120


def test_runtime_resolved_entity_remains_visible_and_grounds_after_crowded_page_context(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    session_id = "v495-ground-from-graph"
    runtime_entity = register_entity(
        session_id,
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Pickaxe",
        canonical_url="https://pickaxe.co",
        artifact_id="bi:search_result:v495:ground",
        selector_ids=["#rso > div:nth-of-type(8)"],
        confidence=0.92,
        source_page="https://search.example.test/results",
    )

    result = SemanticExecutionKernel().postprocess_response(
        result=_open_pickaxe(session_id),
        session_id=session_id,
        task="Open the top relevant result.",
        page_context=_crowded_page(),
        prior_steps=[],
    )

    assert result.outcome_kind == "act", result.replan.reason if result.replan else result.analysis
    assert result.suggested_actions[0].action_type == "open_new_tab"
    assert result.suggested_actions[0].value == "https://pickaxe.co"
    grounded = resolve_entity(session_id, canonical_url="https://pickaxe.co")
    assert grounded is not None
    assert grounded.entity_id == runtime_entity.entity_id
    assert grounded.state == "GROUNDED"
