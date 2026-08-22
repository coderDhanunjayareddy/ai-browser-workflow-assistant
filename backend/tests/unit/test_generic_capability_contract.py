import pytest
from pydantic import ValidationError

from app.contracts.generic_capability import (
    DurableObjective,
    ExpectedEffect,
    GenericCapabilityRequest,
    GenericCapabilityResult,
    TargetIdentity,
)
from app.contracts.registry import CONTRACTS


def _request(**overrides):
    values = {
        "run_id": "run-1", "mission_id": "mission-1", "objective_id": "objective-1",
        "capability_id": "interaction.activate", "family": "interaction",
        "target": TargetIdentity(entity_type="interactive_control", user_supplied_identity="Open details"),
        "expected_effect": ExpectedEffect(
            effect_type="region_opened", observable_postcondition="The requested details region is visible.",
            required_evidence=["visible_region", "target_identity"],
        ),
        "safety_class": "safe", "retry_budget": 1, "idempotency_key": "mission-1:objective-1:activate",
    }
    values.update(overrides)
    return GenericCapabilityRequest(**values)


def test_generic_request_contains_no_application_procedure_or_selector_fields():
    request = _request()
    dumped = request.model_dump()
    assert "application" not in dumped
    assert "selector" not in dumped
    assert request.target.user_supplied_identity == "Open details"


def test_unknown_procedure_fields_are_rejected_instead_of_becoming_core_authority():
    with pytest.raises(ValidationError):
        _request(site_workflow="click the first named-site search result")


def test_consequential_capability_requires_confirmation_and_zero_retry_budget():
    with pytest.raises(ValidationError, match="require confirmation"):
        _request(safety_class="consequential", retry_budget=0, confirmation_required=False)
    with pytest.raises(ValidationError, match="cannot retry"):
        _request(safety_class="consequential", retry_budget=1, confirmation_required=True)
    accepted = _request(safety_class="consequential", retry_budget=0, confirmation_required=True)
    assert accepted.confirmation_required is True


def test_completed_objective_and_verified_result_require_evidence():
    with pytest.raises(ValidationError, match="durable verification evidence"):
        DurableObjective(
            run_id="run-1", mission_id="mission-1", objective_id="objective-1",
            description="Open requested content", required_capabilities=["interaction.activate"], state="completed",
        )
    with pytest.raises(ValidationError, match="requires evidence"):
        GenericCapabilityResult(
            run_id="run-1", mission_id="mission-1", objective_id="objective-1",
            capability_id="interaction.activate", idempotency_key="key-1", outcome="verified_complete",
            user_message="Completed.", latency_ms=10,
        )


def test_duplicate_side_effects_can_never_be_accepted_as_a_result():
    with pytest.raises(ValidationError, match="duplicate side effects"):
        GenericCapabilityResult(
            run_id="run-1", mission_id="mission-1", objective_id="objective-1",
            capability_id="consequential.submit", idempotency_key="key-1", outcome="safely_failed",
            user_message="Stopped after detecting a duplicate.", latency_ms=10, duplicate_side_effects=1,
        )


def test_registry_exposes_generic_objective_request_and_result_contracts():
    names = {descriptor.name for descriptor in CONTRACTS}
    assert {
        "generic_kernel.durable_objective",
        "generic_kernel.capability_request",
        "generic_kernel.capability_result",
    } <= names
