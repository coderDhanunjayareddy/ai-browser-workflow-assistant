from __future__ import annotations

from app.core.config import settings
from app.runtime_state_manager.browser_action_reference import to_browser_tab_reference
from app.runtime_state_manager.completion import artifact_completion_status
from app.runtime_state_manager.engine import RuntimeStateManager
from app.runtime_state_manager.entity_binding import bind_runtime_resource, register_entity, resolve_entity
from app.runtime_state_manager import observe_runtime_state, resolve_logical_tab_url
from app.runtime_state_manager.registry import BrowserRuntimeRegistry
from app.schemas.request import ContentBlock, PageContext, PriorStep
from app.schemas.response import AnalyzeResponse, SuggestedAction


def _page(url: str = "https://example.test/current") -> PageContext:
    return PageContext(
        url=url,
        title="Current Page",
        metadata={},
        interactive_elements=[],
        content_blocks=[
            ContentBlock(selector="#record", text="Visible extracted record", href=url)
        ],
        headings=[],
        selected_text="",
        visible_text="Visible extracted record",
        images=[],
    )


def _open_step(index: int) -> PriorStep:
    return PriorStep(
        action_type="open_new_tab",
        description=f"Open page {index}",
        target_selector="",
        value=f"https://example.test/page-{index}",
        execution_result="success",
        page_url="https://example.test/list",
        page_title="List",
    )


def test_v49_flags_default_to_shadow():
    assert settings.__class__.model_fields["v49_runtime_state_manager"].default == "shadow"
    assert settings.__class__.model_fields["v49_runtime_registry"].default == "shadow"
    assert settings.__class__.model_fields["v49_artifact_engine"].default == "shadow"
    assert settings.__class__.model_fields["v49_runtime_sync"].default == "shadow"
    assert settings.__class__.model_fields["v49_runtime_checkpoints"].default == "shadow"


def test_runtime_registry_builds_logical_tabs_for_multi_tab_workflow(monkeypatch):
    monkeypatch.setattr(settings, "v49_runtime_state_manager", "shadow")
    manager = RuntimeStateManager()

    snapshot = manager.observe(
        session_id="multi-tab",
        page_context=_page("https://example.test/page-2"),
        prior_steps=[_open_step(1), _open_step(2)],
        current_phase="READ",
    )

    assert snapshot is not None
    assert len(snapshot.tabs) == 2
    assert snapshot.focused_tab_id is not None
    assert any(resource.resource_type == "tab" for resource in snapshot.logical_resources)
    assert snapshot.checkpoint.current_phase == "READ"


def test_artifact_registry_and_completion_engine(monkeypatch):
    monkeypatch.setattr(settings, "v49_runtime_state_manager", "shadow")
    manager = RuntimeStateManager()

    snapshot = manager.observe(
        session_id="artifacts",
        page_context=_page(),
        prior_steps=[_open_step(1)],
        current_phase="OPEN",
    )
    status = artifact_completion_status("OPEN", snapshot.artifacts, required_count=1)

    assert status["complete"] is True
    assert status["complete_count"] >= 1
    assert any(artifact.artifact_type == "opened_page" for artifact in snapshot.artifacts)


def test_runtime_consistency_rejects_missing_logical_tab_in_active_mode(monkeypatch):
    monkeypatch.setattr(settings, "v49_runtime_state_manager", "active")
    manager = RuntimeStateManager()
    response = AnalyzeResponse(
        session_id="stale",
        analysis="Focus stale tab.",
        outcome_kind="act",
        clarification_question=None,
        report=None,
        replan=None,
        suggested_actions=[
            SuggestedAction(
                action_id="focus_missing",
                action_type="focus_existing_tab",  # type: ignore[arg-type]
                target_selector="",
                value="logical_tab_missing",
                description="Focus missing logical tab",
                reasoning="Use runtime tab.",
                confidence=0.8,
                safety_level="safe",  # type: ignore[arg-type]
            )
        ],
    )

    snapshot = manager.observe(
        session_id="stale",
        page_context=_page(),
        prior_steps=[],
        current_phase="READ",
        planner_response=response,
    )
    result = manager.postprocess_response(response, snapshot)

    assert snapshot is not None
    assert snapshot.consistency.valid is False
    assert result.outcome_kind == "replan"
    assert "Runtime consistency violation" in result.replan.reason


def test_checkpoint_restore_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "v49_runtime_state_manager", "shadow")
    manager = RuntimeStateManager()
    snapshot = manager.observe(
        session_id="restore",
        page_context=_page(),
        prior_steps=[_open_step(1)],
        current_phase="READ",
    )

    restored = manager.checkpoints.restore("restore")

    assert restored is not None
    assert restored.checkpoint_id == snapshot.checkpoint.checkpoint_id
    assert restored.current_phase == "READ"


def test_registry_restore_survives_runtime_id_changes():
    registry = BrowserRuntimeRegistry()
    windows, tabs = registry.synchronize("restore-tabs", _page("https://example.test/a"), [])
    registry.restore("restore-tabs", tabs, windows)
    same_tab = registry.get_tab("restore-tabs", tabs[0].logical_id)

    assert same_tab is not None
    assert same_tab.logical_id == tabs[0].logical_id


def test_logical_tab_id_stays_internal_but_browser_reference_uses_url():
    session_id = "runtime-tab-reference-contract"
    logical_tab_id = "logical_tab_contract"
    entity = register_entity(
        session_id,
        entity_type="result",
        title="Contract Page",
        canonical_url="https://example.test/contract",
        source_layer="test",
    )

    bind_runtime_resource(
        session_id,
        entity_id=entity.entity_id,
        runtime_resource_id=logical_tab_id,
    )

    stored = resolve_entity(session_id, runtime_resource_id=logical_tab_id)

    assert stored is not None
    assert stored.runtime_resource_id == logical_tab_id
    assert to_browser_tab_reference(session_id, logical_tab_id) == "url:https://example.test/contract"
    assert to_browser_tab_reference(session_id, "https://example.test/contract") == "url:https://example.test/contract"
    assert to_browser_tab_reference(session_id, "title:Contract Page") == "title:Contract Page"


def test_logical_tab_reference_resolves_from_runtime_state_without_entity_binding(monkeypatch):
    monkeypatch.setattr(settings, "v49_runtime_state_manager", "shadow")
    monkeypatch.setattr(settings, "v49_runtime_sync", "shadow")
    session_id = "runtime-tab-reference-from-tabs"
    prior = [
        PriorStep(
            action_type="open_new_tab",
            description="Open result",
            target_selector="",
            value="https://example.test/opened",
            execution_result="Opened new tab: https://example.test/opened",
            page_url="https://search.example/results",
            page_title="Search Results",
        )
    ]
    snapshot = observe_runtime_state(
        session_id=session_id,
        page_context=_page("https://search.example/results"),
        prior_steps=prior,
        current_phase="READ",
    )

    opened_tab = next(tab for tab in snapshot.tabs if tab.url == "https://example.test/opened")

    assert opened_tab.logical_id.startswith("logical_tab_")
    assert resolve_logical_tab_url(session_id, opened_tab.logical_id) == "https://example.test/opened"
    assert to_browser_tab_reference(session_id, opened_tab.logical_id) == "url:https://example.test/opened"
