from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.intervention import (
    HumanInterventionRequest,
    HumanInterventionResume,
    ResumeCondition,
)
from app.contracts.registry import CONTRACTS


def request(**overrides) -> HumanInterventionRequest:
    payload = {
        "run_id": "run-1",
        "intervention_id": "intervention-1",
        "mission_id": "mission-1",
        "objective_id": "objective-auth",
        "kind": "authentication",
        "reason_code": "authentication_required",
        "user_message": "Please sign in directly in the browser, then continue.",
        "requested_action": "Complete the visible sign-in step in the browser.",
        "secret_handling": "direct_browser_only",
        "checkpoint_ref": "checkpoint-1",
        "completed_objective_ids": ["objective-open"],
        "pending_objective_ids": ["objective-auth", "objective-search"],
        "resume_condition": ResumeCondition(
            evidence_kind="authenticated_state",
            expected_value="authenticated workspace is visible",
            observed_origin="https://example.test",
            tab_id=7,
        ),
    }
    payload.update(overrides)
    return HumanInterventionRequest(**payload)


def test_intervention_contract_is_domain_independent_and_checkpointed() -> None:
    payload = request().model_dump(mode="json")

    assert payload["schema_version"] == "human_intervention.request.v1"
    assert payload["producer"] == "backend.generic_capability_kernel"
    assert payload["secret_handling"] == "direct_browser_only"
    assert payload["request_budget"] == 1
    assert payload["completed_objective_ids"] == ["objective-open"]
    assert payload["pending_objective_ids"] == ["objective-auth", "objective-search"]
    assert not any(name in str(payload).casefold() for name in ("whatsapp", "gmail", "linkedin"))


def test_sensitive_intervention_cannot_request_secret_through_assistant() -> None:
    with pytest.raises(ValidationError, match="directly in the browser"):
        request(secret_handling="non_sensitive_response_allowed")


def test_completed_and_pending_objectives_cannot_overlap() -> None:
    with pytest.raises(ValidationError, match="disjoint"):
        request(completed_objective_ids=["objective-open"], pending_objective_ids=["objective-open"])


def test_resume_requires_observed_evidence_and_exactly_once_state() -> None:
    resumed = HumanInterventionResume(
        run_id="run-1",
        intervention_id="intervention-1",
        checkpoint_ref="checkpoint-1",
        satisfied=True,
        evidence_kind="authenticated_state",
        observed_value="authenticated workspace is visible",
        observed_origin="https://example.test",
        tab_id=7,
        resumed_objective_id="objective-search",
    )
    assert resumed.duplicate_dispatch_prevented is True

    with pytest.raises(ValidationError, match="exactly-once"):
        HumanInterventionResume(
            run_id="run-1",
            intervention_id="intervention-1",
            checkpoint_ref="checkpoint-1",
            satisfied=True,
            evidence_kind="authenticated_state",
            observed_value="authenticated workspace is visible",
            observed_origin="https://example.test",
            tab_id=7,
            resumed_objective_id="objective-search",
            duplicate_dispatch_prevented=False,
        )


def test_contract_registry_exposes_intervention_request_and_resume() -> None:
    names = {contract.name for contract in CONTRACTS}
    assert "generic_kernel.human_intervention_request" in names
    assert "generic_kernel.human_intervention_resume" in names
