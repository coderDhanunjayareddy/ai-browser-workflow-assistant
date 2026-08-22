from types import SimpleNamespace

import pytest

from app.semantic_execution_kernel.capability_contracts import compile_capability_request


def _action(**overrides):
    values = {
        "action_id": "action-1", "intent_id": "intent-1", "action_type": "click",
        "target_selector": "[data-runtime-id='observed-1']", "safety_level": "safe",
        "grounding": {"origin": "https://example.test", "tab_id": 7, "frame_id": "top"},
        "content_insertion": None, "consequential_submission": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_compiler_maps_a_generic_observed_action_without_application_knowledge():
    request = compile_capability_request(
        action=_action(), mission_id="mission-1", objective_id="objective-1",
        objective_identity="Open details", run_id="run-1",
    )
    assert request.capability_id == "interaction.activate"
    assert request.target.user_supplied_identity == "Open details"
    assert request.target.allowed_origin == "https://example.test"
    assert request.inputs["live_grounding_required"] is True
    assert "example" not in request.capability_id


def test_compiler_converts_consequential_declaration_to_confirmed_zero_retry_operation():
    request = compile_capability_request(
        action=_action(
            safety_level="danger",
            consequential_submission={"content_identity": "approved-resource-1"},
        ),
        mission_id="mission-1", objective_id="objective-send", objective_identity="Exact recipient",
        run_id="run-1",
    )
    assert request.family == "consequential_operation"
    assert request.confirmation_required is True
    assert request.retry_budget == 0
    assert request.inputs["content_identity"] == "approved-resource-1"
    assert request.target.exact_match_required is True


def test_compiler_rejects_unknown_actions_instead_of_guessing_a_named_workflow():
    with pytest.raises(ValueError, match="Unsupported generic action type"):
        compile_capability_request(
            action=_action(action_type="provider_specific_magic"), mission_id="mission-1",
            objective_id="objective-1", objective_identity=None, run_id="run-1",
        )


def test_idempotency_identity_is_stable_for_same_mission_objective_and_intent():
    first = compile_capability_request(
        action=_action(action_id="planner-a"), mission_id="mission-1", objective_id="objective-1",
        objective_identity=None, run_id="run-1",
    )
    regenerated = compile_capability_request(
        action=_action(action_id="planner-b"), mission_id="mission-1", objective_id="objective-1",
        objective_identity=None, run_id="run-2",
    )
    assert first.idempotency_key == regenerated.idempotency_key
