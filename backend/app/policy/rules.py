from __future__ import annotations

from app.schemas.response import SuggestedAction


DESTRUCTIVE_TERMS = {
    "delete",
    "remove",
    "destroy",
    "cancel subscription",
    "close account",
}
IRREVERSIBLE_TERMS = {
    "purchase",
    "buy",
    "payment",
    "pay",
    "checkout",
    "place order",
    "send",
    "submit",
    "post",
    "share",
    "publish",
}
HANDOFF_TERMS = {
    "password",
    "otp",
    "2fa",
    "two factor",
    "captcha",
    "security code",
    "credit card",
    "ssn",
}


def classify_action_risk(action: SuggestedAction) -> tuple[str, list[str], list[str]]:
    text = _action_text(action)
    approval_hooks: list[str] = []
    reasons: list[str] = []

    if action.safety_level == "danger":
        reasons.append("planner_marked_danger")
    if any(term in text for term in DESTRUCTIVE_TERMS):
        approval_hooks.append("destructive_action")
        reasons.append("destructive_action_detected")
    if any(term in text for term in IRREVERSIBLE_TERMS):
        approval_hooks.append("irreversible_external_action")
        reasons.append("irreversible_action_detected")
    if action.action_type in {"close_tab"}:
        approval_hooks.append("tab_close")
        reasons.append("tab_close_requires_policy_check")
    if action.action_type in {"fill"} and any(term in text for term in HANDOFF_TERMS):
        approval_hooks.append("sensitive_input")
        reasons.append("sensitive_input_detected")
    if "upload" in text:
        approval_hooks.append("file_upload")
        reasons.append("file_upload_detected")
    if "download" in text:
        reasons.append("file_download_detected")

    if any(term in text for term in HANDOFF_TERMS):
        return "critical", approval_hooks, reasons or ["sensitive_context"]
    if action.safety_level == "danger" or "destructive_action" in approval_hooks:
        return "critical", approval_hooks, reasons
    if approval_hooks:
        return "danger", approval_hooks, reasons
    if action.safety_level == "caution":
        return "caution", approval_hooks, reasons or ["planner_marked_caution"]
    return "safe", approval_hooks, reasons or ["low_risk_action"]


def _action_text(action: SuggestedAction) -> str:
    return " ".join(
        value.lower()
        for value in [
            action.action_type,
            action.target_selector,
            action.value or "",
            action.description,
            action.reasoning,
        ]
        if value
    )
