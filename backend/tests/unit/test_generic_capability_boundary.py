from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.semantic_execution_kernel.capability_boundary import bind_capability_contracts


def _response(action_type="click", **action_overrides):
    action_values = {
        "action_id": "action-1", "intent_id": "intent-1", "mission_id": "mission-1",
        "action_type": action_type, "target_selector": "[data-runtime-id='one']", "value": None,
        "description": "Activate the observed control", "reasoning": "Required by objective",
        "confidence": 0.9, "safety_level": "safe",
        "grounding": {"origin": "https://example.test", "accessible_name": "Open details"},
    }
    action_values.update(action_overrides)
    return AnalyzeResponse(
        session_id="mission-1", analysis="Observed a compatible control.",
        suggested_actions=[SuggestedAction(**action_values)],
    )


def test_final_boundary_contracts_deterministic_and_planner_actions_equally():
    result = bind_capability_contracts(_response(), session_id="mission-1", task="Open details")
    assert result.capability_contract_violations == []
    assert len(result.capability_contracts) == 1
    contract = result.capability_contracts[0]
    assert contract["capability_id"] == "interaction.activate"
    assert contract["target"]["user_supplied_identity"] == "Open details"


def test_final_boundary_preserves_exact_destination_from_consequential_declaration():
    result = bind_capability_contracts(
        _response(
            safety_level="danger",
            consequential_submission={
                "submission_id": "submission-1", "destination_entity": "Exact destination",
                "content_identity": "approved-content-1",
            },
        ),
        session_id="mission-1", task="Submit approved content",
    )
    contract = result.capability_contracts[0]
    assert contract["target"]["user_supplied_identity"] == "Exact destination"
    assert contract["confirmation_required"] is True
    assert contract["retry_budget"] == 0


def test_unknown_action_is_visible_as_contract_violation_and_never_guessed():
    result = bind_capability_contracts(
        _response(action_type="provider_specific_magic"),
        session_id="mission-1", task="Do something unsupported",
    )
    assert result.capability_contracts == []
    assert result.capability_contract_violations[0]["action_type"] == "provider_specific_magic"
    assert "Unsupported generic action type" in result.capability_contract_violations[0]["reason"]
