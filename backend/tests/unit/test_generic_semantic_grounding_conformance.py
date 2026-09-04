from __future__ import annotations

import random

from app.grounding import GroundingResolver
from app.orchestrator.workflow_orchestrator import _enforce_authoritative_semantic_grounding
from app.schemas.request import InteractiveElement, PageContext
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.semantic_page.builder import SemanticPageGraphBuilder, observation_hash


def _page(elements: list[InteractiveElement], *, frame_id: str = "top") -> PageContext:
    return PageContext(
        tab_id=17,
        window_id=4,
        frame_id=frame_id,
        url="https://unfamiliar.example/workspace",
        title="Synthetic workspace",
        interactive_elements=elements,
        selected_text="",
        visible_text="Synthetic workspace",
    )


def _button(label: str, selector: str, **kwargs) -> InteractiveElement:
    return InteractiveElement(
        type="button",
        text=kwargs.pop("text", label),
        accessibility_name=label,
        selector=selector,
        visible=kwargs.pop("visible", True),
        bounding_box=kwargs.pop("bounding_box", {"x": 10, "y": 10, "width": 80, "height": 30}),
        **kwargs,
    )


def _click(label: str, selector: str = "") -> SuggestedAction:
    return SuggestedAction(
        action_id="act",
        action_type="click",
        target_selector=selector,
        description="Activate the requested control",
        reasoning="Use the exact currently observed control",
        confidence=0.9,
        safety_level="safe",
        grounding={"accessibility_name": label},
    )


def test_randomized_dom_order_preserves_exact_accessible_identity():
    base = [
        _button("Continue", "#continue"),
        _button("Continue later", "#later"),
        _button("Cancel", "#cancel"),
    ]
    resolver = GroundingResolver()
    for seed in range(40):
        elements = list(base)
        random.Random(seed).shuffle(elements)
        result = resolver.resolve(
            run_id=f"seed-{seed}",
            action=_click("Continue"),
            graph=SemanticPageGraphBuilder().build(_page(elements)),
        )
        assert result.status == "resolved"
        assert result.selected_selector == "#continue"


def test_visible_disabled_and_zero_area_controls_are_evidence_not_targets():
    page = _page([
        _button("Publish", "#disabled", state={"disabled": True}),
        _button("Publish", "#zero", bounding_box={"x": 0, "y": 0, "width": 0, "height": 0}),
    ])
    graph = SemanticPageGraphBuilder().build(page)

    assert len([node for node in graph.nodes if node.node_type == "control"]) == 2
    assert graph.targets == []
    assert GroundingResolver().resolve(run_id="disabled", action=_click("Publish"), graph=graph).status == "not_found"


def test_unrelated_descendant_prose_does_not_become_generic_container_identity():
    container = InteractiveElement(
        type="div",
        role="row",
        text="Quarterly report contains Publish and Delete prose but this row has no accessible name",
        accessibility_name="",
        selector="#row",
        visible=True,
        bounding_box={"x": 1, "y": 1, "width": 300, "height": 80},
    )
    graph = SemanticPageGraphBuilder().build(_page([container]))
    assert graph.targets[0].label == ""
    result = GroundingResolver().resolve(run_id="descendant", action=_click("Delete"), graph=graph)
    assert result.status == "not_found"


def test_readonly_field_cannot_be_selected_for_fill():
    field = InteractiveElement(
        type="input",
        text="",
        selector="#account-id",
        visible=True,
        input_type="text",
        accessibility_name="Account ID",
        state={"readonly": True},
        bounding_box={"x": 5, "y": 5, "width": 100, "height": 24},
    )
    action = SuggestedAction(
        action_id="fill",
        action_type="fill",
        target_selector="#account-id",
        value="synthetic",
        description="Fill Account ID",
        reasoning="Use the observed field",
        confidence=0.9,
        safety_level="safe",
        grounding={"accessibility_name": "Account ID"},
    )

    result = GroundingResolver().resolve(run_id="readonly", action=action, graph=SemanticPageGraphBuilder().build(_page([field])))
    assert result.status == "not_found"


def test_duplicate_exact_labels_fail_closed_as_ambiguous():
    graph = SemanticPageGraphBuilder().build(_page([
        _button("Open", "#first"),
        _button("Open", "#second"),
    ]))
    result = GroundingResolver().resolve(run_id="ambiguous", action=_click("Open"), graph=graph)
    assert result.status == "ambiguous"
    assert {candidate.locator_candidates[0] for candidate in result.candidates} == {"#first", "#second"}


def test_selector_binding_preserves_tab_window_frame_origin_and_geometry():
    page = _page([_button("Continue", "#continue")], frame_id="frame.checkout")
    response = AnalyzeResponse(
        session_id="binding",
        analysis="",
        suggested_actions=[_click("Continue", "#continue")],
    )

    grounded = _enforce_authoritative_semantic_grounding(session_id="binding", result=response, page_context=page)
    binding = grounded.suggested_actions[0].grounding
    assert binding["tab_id"] == 17
    assert binding["window_id"] == 4
    assert binding["frame_id"] == "frame.checkout"
    assert binding["origin"] == "https://unfamiliar.example"
    assert binding["bounding_box"]["width"] == 80
    assert binding["source"] == "semantic_page_graph"


def test_stale_selector_rebinds_by_unique_exact_accessible_identity():
    page = _page([_button("Continue", "#current")])
    response = AnalyzeResponse(
        session_id="stale",
        analysis="",
        suggested_actions=[_click("Continue", "#stale")],
    )

    grounded = _enforce_authoritative_semantic_grounding(session_id="stale", result=response, page_context=page)
    assert grounded.outcome_kind == "act"
    assert grounded.suggested_actions[0].target_selector == "#current"
    assert "exact_accessible_identity" not in grounded.suggested_actions[0].grounding


def test_stale_selector_with_duplicate_identity_is_blocked_before_browser_handoff():
    page = _page([_button("Continue", "#first"), _button("Continue", "#second")])
    response = AnalyzeResponse(
        session_id="stale-ambiguous",
        analysis="",
        suggested_actions=[_click("Continue", "#stale")],
    )

    grounded = _enforce_authoritative_semantic_grounding(
        session_id="stale-ambiguous", result=response, page_context=page
    )
    assert grounded.outcome_kind == "ask"
    assert grounded.suggested_actions == []
    assert "No browser mutation was dispatched" in grounded.analysis


def test_observation_identity_changes_with_frame_geometry_and_state():
    baseline = _page([_button("Continue", "#continue")])
    moved = _page([_button("Continue", "#continue", bounding_box={"x": 200, "y": 10, "width": 80, "height": 30})])
    framed = _page([_button("Continue", "#continue")], frame_id="frame.other")
    disabled = _page([_button("Continue", "#continue", state={"disabled": True})])

    hashes = {observation_hash(item) for item in (baseline, moved, framed, disabled)}
    assert len(hashes) == 4
