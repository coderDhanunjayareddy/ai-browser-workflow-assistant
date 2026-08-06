from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


SubmitPolicy = Literal["never_submit", "sandbox_only", "approval_required"]


@dataclass(frozen=True)
class FormWorkflowSpec:
    schema_version: str
    workflow_type: Literal["form_workflow", "signup_workflow"]
    requires_fake_data: bool
    requires_validation_pass: bool
    submit_policy: SubmitPolicy
    blocked_submit_reasons: list[str] = field(default_factory=list)
    requested_fields: list[str] = field(default_factory=list)
    evidence_required: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_form_workflow_spec(task: str) -> FormWorkflowSpec:
    text = " ".join(str(task or "").split()).lower()
    workflow_type: Literal["form_workflow", "signup_workflow"] = "signup_workflow" if _has(text, "signup", "sign up", "create account", "free account", "free trial") else "form_workflow"
    sandbox = _has(text, "sandbox", "test form", "demo form", "public test")
    final_submit_requested = _has(text, "submit", "send")
    official_or_real = _has(text, "government", "legal", "official", "real ", "production", "account", "signup", "sign up")

    submit_policy: SubmitPolicy = "never_submit"
    blocked: list[str] = []
    if final_submit_requested and sandbox:
        submit_policy = "sandbox_only"
    elif final_submit_requested:
        submit_policy = "approval_required"
        blocked.append("final_submit_requires_explicit_sandbox_or_user_approval")
    if official_or_real and not sandbox:
        blocked.append("real_or_official_form_submit_blocked_without_approval")

    return FormWorkflowSpec(
        schema_version="form_workflow_spec.v1",
        workflow_type=workflow_type,
        requires_fake_data=_has(text, "fake", "test data", "dummy", "sample") or workflow_type == "form_workflow",
        requires_validation_pass=_has(text, "validation", "valid", "errors", "fix") or final_submit_requested,
        submit_policy=submit_policy,
        blocked_submit_reasons=_dedupe(blocked),
        requested_fields=_requested_form_fields(text),
        evidence_required=[
            "form_fields_detected",
            "field_mapping",
            "filled_field_count",
            "constraint_validation_result",
            "submit_policy_decision",
        ],
    )


def _requested_form_fields(text: str) -> list[str]:
    aliases = {
        "name": ("name", "full name"),
        "email": ("email", "test email"),
        "phone": ("phone", "mobile"),
        "company": ("company", "organization"),
        "message": ("message", "comments", "description"),
        "password": ("password",),
        "profile": ("profile",),
        "billing": ("billing", "plan"),
    }
    fields: list[str] = []
    for field, needles in aliases.items():
        if any(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", text) for needle in needles):
            fields.append(field)
    return fields


def _has(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return out
