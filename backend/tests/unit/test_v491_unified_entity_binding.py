from __future__ import annotations

from app.core.config import settings
from app.runtime_state_manager.engine import RuntimeStateManager
from app.runtime_state_manager.entity_binding import list_entities, register_entity, resolve_entity
from app.schemas.request import ContentBlock, PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.semantic_execution_kernel.engine import SemanticExecutionKernel


def _blank_page(url: str = "https://search.example.test/results") -> PageContext:
    return PageContext(
        url=url,
        title="Search Results",
        metadata={},
        interactive_elements=[],
        content_blocks=[ContentBlock(selector="#summary", text="Results page", href=url)],
        headings=["Results"],
        selected_text="",
        visible_text="Results page",
        images=[],
    )


def _response(value: str) -> AnalyzeResponse:
    return AnalyzeResponse(
        session_id="binding-session",
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
                value=value,
                description="Open registered result",
                reasoning="Planner selected explicit URL.",
                confidence=0.9,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )


def test_registered_canonical_url_survives_kernel_turn_and_grounds_open_new_tab(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")
    register_entity(
        "binding-session",
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Pickaxe",
        canonical_url="https://pickaxe.co",
        artifact_id="bi:search_result:test:1",
        confidence=0.92,
        source_page="https://search.example.test/results",
    )

    result = SemanticExecutionKernel().postprocess_response(
        result=_response("https://pickaxe.co"),
        session_id="binding-session",
        task="Open the top relevant result.",
        page_context=_blank_page(),
        prior_steps=[],
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "open_new_tab"
    assert result.suggested_actions[0].value == "https://pickaxe.co"
    entity = resolve_entity("binding-session", canonical_url="https://pickaxe.co")
    assert entity is not None
    assert entity.state == "GROUNDED"


def test_safe_explicit_url_is_registered_by_kernel_instead_of_entity_missing(monkeypatch):
    monkeypatch.setattr(settings, "v47_semantic_execution_kernel", "active")

    result = SemanticExecutionKernel().postprocess_response(
        result=_response("https://untrusted.example.test"),
        session_id="binding-unregistered",
        task="Open the top relevant result.",
        page_context=_blank_page(),
        prior_steps=[],
    )

    assert result.outcome_kind == "act"
    assert result.suggested_actions[0].action_type == "open_new_tab"
    assert result.suggested_actions[0].value == "https://untrusted.example.test"


def test_runtime_state_maps_opened_tab_to_registered_entity(monkeypatch):
    monkeypatch.setattr(settings, "v49_runtime_state_manager", "active")
    monkeypatch.setattr(settings, "v49_runtime_sync", "active")
    register_entity(
        "binding-runtime",
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Pickaxe",
        canonical_url="https://pickaxe.co",
        artifact_id="bi:search_result:test:runtime",
        confidence=0.92,
        source_page="https://search.example.test/results",
    )
    prior = [
        PriorStep(
            action_type="open_new_tab",
            description="Open registered URL",
            target_selector="",
            value="https://pickaxe.co",
            execution_result="success",
            page_url="https://search.example.test/results",
            page_title="Search Results",
        )
    ]

    snapshot = RuntimeStateManager().observe(
        session_id="binding-runtime",
        page_context=_blank_page("https://pickaxe.co"),
        prior_steps=prior,
        current_phase="READ",
    )

    assert snapshot is not None
    entity = resolve_entity("binding-runtime", canonical_url="https://pickaxe.co")
    assert entity is not None
    assert entity.runtime_resource_id is not None
    assert any(resource.mission_entity_id == entity.entity_id for resource in snapshot.logical_resources)


def test_no_duplicate_entities_for_same_canonical_url():
    first = register_entity(
        "binding-dedupe",
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Pickaxe",
        canonical_url="https://pickaxe.co/",
        artifact_id="bi:search_result:test:dedupe-1",
        confidence=0.8,
    )
    second = register_entity(
        "binding-dedupe",
        entity_type="search_result",
        source_layer="browser_intelligence",
        title="Pickaxe AI",
        canonical_url="https://pickaxe.co",
        artifact_id="bi:search_result:test:dedupe-2",
        confidence=0.9,
    )

    assert first.entity_id == second.entity_id
    assert len([entity for entity in list_entities("binding-dedupe") if entity.canonical_url == "https://pickaxe.co"]) == 1
