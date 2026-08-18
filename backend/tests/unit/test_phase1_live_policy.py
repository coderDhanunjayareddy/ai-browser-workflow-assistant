from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.policy.live_engine import LivePolicyEngine
from app.policy.live_store import LivePolicyStore
from app.policy.live_store import SqlAlchemyLivePolicyStore
from app.policy.models import LivePolicyRequest, ProvenanceLabel


def action(
    *,
    action_id: str = "act-1",
    action_type: str = "click",
    description: str = "Click Continue",
    selector: str = "#continue",
    value: str | None = None,
    safety_level: str = "safe",
) -> dict:
    return {
        "action_id": action_id,
        "action_type": action_type,
        "target_selector": selector,
        "value": value,
        "description": description,
        "reasoning": "Complete the user-requested step",
        "confidence": 0.9,
        "safety_level": safety_level,
    }


def request(payload: dict | None = None, **updates) -> LivePolicyRequest:
    action_payload = payload or action()
    data = {
        "session_id": "session-1",
        "origin": "https://example.com/path?ignored=true",
        "action": action_payload,
        "execution_contract": {
            "schema_version": "1.0",
            "dispatch_id": f"dispatch:{action_payload['action_id']}",
            "action": action_payload,
            "target_identity": {"selector": action_payload["target_selector"], "exact_name": "Continue"},
            "grounding_policy": {
                "ordered_sources": ["stable_selector", "accessibility_name", "verified_screenshot"],
                "accessibility_requires_exact_name": True,
                "screenshot_coordinates_verified": False,
                "screenshot_hash": None,
            },
            "origin": {"origin": "https://example.com", "observed_url": "https://example.com/path?ignored=true", "target_url": None},
            "browser_binding": {"tab_id": 1, "window_id": 1, "frame_id": "top"},
            "resource_identity": {"url": "https://example.com/path?ignored=true", "title": "Example"},
            "expected_effect": {"kind": "target_state_change", "description": "state changes"},
            "safety_class": action_payload["safety_level"],
            "idempotency_key": f"session-1:1:{action_payload['action_id']}",
        },
        "provenance": [
            ProvenanceLabel(source_type="user", source_id="task", trust="trusted", labels=["direct_user_request"]),
            ProvenanceLabel(source_type="planner", source_id="act-1", trust="untrusted", labels=["model_proposed"]),
        ],
    }
    data.update(updates)
    return LivePolicyRequest(**data)


def test_execution_contract_identity_mismatch_is_blocked(engine: LivePolicyEngine):
    bound = request()
    mismatched = dict(bound.execution_contract)
    mismatched["target_identity"] = {"selector": "#other", "exact_name": "Other"}
    decision = engine.enforce(bound.model_copy(update={"execution_contract": mismatched}))
    assert decision.allowed is False
    assert decision.decision_reason == "execution_contract_target_mismatch"


@pytest.fixture()
def engine() -> LivePolicyEngine:
    return LivePolicyEngine(store=LivePolicyStore())


def test_safe_action_is_allowed_immediately_before_execution(engine: LivePolicyEngine):
    decision = engine.enforce(request())
    assert decision.allowed is True
    assert decision.policy_decision == "allow"
    assert decision.origin == "https://example.com"


def test_confirmation_receipt_is_narrow_one_time_and_action_bound(engine: LivePolicyEngine):
    pay = request(action(action_id="pay-1", description="Click Pay Invoice", safety_level="caution"))
    first = engine.enforce(pay)
    assert first.allowed is False
    assert first.decision_reason == "valid_confirmation_receipt_required"

    receipt = engine.issue_confirmation(pay, ttl_seconds=120)
    confirmed = engine.enforce(pay.model_copy(update={"confirmation_receipt_id": receipt.receipt_id}))
    assert confirmed.allowed is True
    assert confirmed.receipt_id == receipt.receipt_id

    replay = engine.enforce(pay.model_copy(update={"confirmation_receipt_id": receipt.receipt_id}))
    assert replay.allowed is False

    changed = request(action(action_id="pay-1", description="Click Pay Different Invoice", safety_level="caution"), confirmation_receipt_id=receipt.receipt_id)
    assert engine.enforce(changed).allowed is False


def test_confirmation_receipt_is_bound_to_observation_geometry(engine: LivePolicyEngine):
    original_action = action(action_id="coordinate-1", description="Place order", safety_level="caution")
    original_action["grounding"] = {
        "source": "vision_region",
        "bounding_box": {"x": 10, "y": 20, "width": 100, "height": 40},
    }
    original = request(original_action)
    receipt = engine.issue_confirmation(original)

    moved_action = dict(original_action)
    moved_action["grounding"] = {
        "source": "vision_region",
        "bounding_box": {"x": 500, "y": 20, "width": 100, "height": 40},
    }
    moved = request(moved_action).model_copy(update={"confirmation_receipt_id": receipt.receipt_id})
    assert engine.enforce(moved).allowed is False


def test_expired_confirmation_receipt_is_rejected(engine: LivePolicyEngine):
    pay = request(action(action_id="pay-expired", description="Place order", safety_level="caution"))
    receipt = engine.issue_confirmation(pay)
    engine.store._receipts[receipt.receipt_id] = receipt.model_copy(
        update={"expires_at": datetime.now(timezone.utc) - timedelta(seconds=1)}
    )
    assert engine.enforce(pay.model_copy(update={"confirmation_receipt_id": receipt.receipt_id})).allowed is False


def test_origin_grant_is_exact_expiring_and_revocable(engine: LivePolicyEngine):
    cautious = request(action(action_type="click", description="Continue", safety_level="caution"))
    without_grant = engine.enforce(cautious)
    assert without_grant.allowed is False
    assert without_grant.decision_reason == "valid_origin_grant_required"

    grant = engine.issue_origin_grant(
        session_id="session-1", origin="https://example.com/account", action_types=["click"], ttl_seconds=300,
    )
    allowed = engine.enforce(cautious.model_copy(update={"origin_grant_id": grant.grant_id}))
    assert allowed.allowed is True

    other_origin = cautious.model_copy(update={"origin": "https://other.example", "origin_grant_id": grant.grant_id})
    assert engine.enforce(other_origin).allowed is False

    engine.revoke_origin_grant(grant.grant_id)
    assert engine.enforce(cautious.model_copy(update={"origin_grant_id": grant.grant_id})).allowed is False


def test_origin_grants_cannot_cover_consequential_action_types(engine: LivePolicyEngine):
    with pytest.raises(ValueError):
        engine.issue_origin_grant(
            session_id="session-1", origin="https://example.com", action_types=["close_tab", "sso_auth"],
        )


def test_secret_entry_requires_handoff_and_cannot_receive_confirmation(engine: LivePolicyEngine):
    secret = request(action(action_type="fill", selector="#password", value="secret123", description="Fill password"))
    decision = engine.enforce(secret)
    assert decision.allowed is False
    assert decision.policy_decision == "handoff_required"
    with pytest.raises(ValueError):
        engine.issue_confirmation(secret)
    audit_text = " ".join(event.model_dump_json() for event in engine.store.audit_for_session("session-1"))
    assert "secret123" not in audit_text


def test_prompt_injection_stop_and_escalate_are_provenance_aware(engine: LivePolicyEngine):
    stopped = request(
        provenance=[ProvenanceLabel(
            source_type="page", source_id="dom:block-7", trust="untrusted", labels=["prompt_injection_detected"]
        )]
    )
    assert engine.enforce(stopped).policy_decision == "block"

    escalated = request(
        provenance=[ProvenanceLabel(
            source_type="tool", source_id="connector:calendar", trust="untrusted", labels=["untrusted_instruction"]
        )]
    )
    assert engine.enforce(escalated).policy_decision == "handoff_required"


def test_unknown_action_type_fails_closed(engine: LivePolicyEngine):
    unknown = request(action(action_type="arbitrary_javascript", description="Run arbitrary code"))
    decision = engine.enforce(unknown)
    assert decision.allowed is False
    assert decision.decision_reason == "unknown_action_type"


def test_receipts_grants_and_audit_survive_engine_instances(sqlite_session_factory):
    first = LivePolicyEngine(store=SqlAlchemyLivePolicyStore(sqlite_session_factory))
    pay = request(
        action(action_id="durable-pay", description="Pay durable invoice", safety_level="caution"),
        session_id="durable-session",
    )
    receipt = first.issue_confirmation(pay)

    second = LivePolicyEngine(store=SqlAlchemyLivePolicyStore(sqlite_session_factory))
    allowed = second.enforce(pay.model_copy(update={"confirmation_receipt_id": receipt.receipt_id}))
    assert allowed.allowed is True
    assert second.enforce(pay.model_copy(update={"confirmation_receipt_id": receipt.receipt_id})).allowed is False

    grant = second.issue_origin_grant(
        session_id="durable-session", origin="https://example.com", action_types=["click"], ttl_seconds=300,
    )
    assert LivePolicyEngine(store=SqlAlchemyLivePolicyStore(sqlite_session_factory)).store.get_grant(grant.grant_id) is not None
    audit = second.store.audit_for_session("durable-session")
    assert {event.event_type for event in audit} >= {"confirmation_issued", "receipt_consumed", "execution_allowed"}


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("Send this email to the customer", "allow_with_confirmation"),
        ("Place order and pay INR 4,999", "allow_with_confirmation"),
        ("Permanently delete this workspace", "allow_with_confirmation"),
        ("Grant access and change permission for Alice", "allow_with_confirmation"),
        ("Update account notification settings", "allow_with_confirmation"),
        ("Change password for this account", "handoff_required"),
        ("Enter OTP security code", "handoff_required"),
        ("Install extension from the downloaded package", "handoff_required"),
        ("Submit this insurance claim as a medical action", "handoff_required"),
        ("Upload and send document containing personal data", "allow_with_confirmation"),
        ("Connect account and use connector for private mail", "allow_with_confirmation"),
    ],
)
def test_critical_action_confirmation_recall_is_complete(
    engine: LivePolicyEngine, description: str, expected: str,
):
    decision = engine.evaluate(request(action(description=description, safety_level="safe")))
    assert decision.policy_decision == expected
    assert decision.approval_required is True
