from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SignupSubmitGate = Literal["test_email_only", "explicit_approval_required", "blocked"]


@dataclass(frozen=True)
class SignupWorkflowPolicy:
    schema_version: str
    requires_test_email: bool
    submit_gate: SignupSubmitGate
    max_accounts_per_mission: int
    blocked_actions: list[str] = field(default_factory=list)
    external_stop_conditions: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_signup_workflow_policy(task: str) -> SignupWorkflowPolicy:
    text = " ".join(str(task or "").split()).lower()
    has_test_email = any(term in text for term in ("test email", "email you control", "fake email", "sandbox email"))
    explicitly_signup = any(term in text for term in ("signup", "sign up", "create account", "free account", "free trial", "register"))
    payment_terms = ("payment", "checkout", "billing checkout", "credit card", "card number")
    security_terms = ("change password", "password change", "security setting", "delete account", "close account")

    blocked = ["payment_or_checkout", "password_or_security_change", "email_verification_bypass"]
    if any(term in text for term in payment_terms):
        blocked.append("payment_requested_in_signup_flow")
    if any(term in text for term in security_terms):
        blocked.append("account_security_change_requested")

    if not explicitly_signup:
        submit_gate: SignupSubmitGate = "blocked"
    elif has_test_email:
        submit_gate = "test_email_only"
    else:
        submit_gate = "explicit_approval_required"

    return SignupWorkflowPolicy(
        schema_version="signup_workflow_policy.v1",
        requires_test_email=True,
        submit_gate=submit_gate,
        max_accounts_per_mission=1,
        blocked_actions=_dedupe(blocked),
        external_stop_conditions=["email_verification_required", "captcha_or_bot_check", "phone_verification_required"],
        required_evidence=[
            "test_email_source",
            "signup_form_fields_filled",
            "submit_gate_decision",
            "welcome_or_dashboard_state",
            "profile_page_evidence",
            "billing_or_plan_page_evidence",
        ],
    )


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
