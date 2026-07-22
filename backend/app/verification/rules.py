from __future__ import annotations

from app.verification.models import FailureCategory, ValidationEvidence, ValidationStatus


def evaluate_report_rule(
    *,
    answer: str | None,
    evidence: list[ValidationEvidence],
) -> tuple[ValidationStatus, float, FailureCategory | None, list[str], list[str]]:
    answer_text = (answer or "").strip()
    if not answer_text:
        return "uncertain", 0.2, "missing_target", ["specific_report_answer"], ["specific_report_answer"]
    corpus = "\n".join(item.value for item in evidence).lower()
    if answer_text.lower() in corpus:
        return "satisfied", 0.95, None, [answer_text], []
    if corpus:
        return "not_satisfied", 0.75, "missing_target", [], [answer_text]
    return "uncertain", 0.3, "unknown", [], [answer_text]


def evaluate_execution_rule(
    *,
    action_type: str,
    success: bool,
    execution_result: str,
    before_url: str | None = None,
    after_url: str | None = None,
) -> tuple[ValidationStatus, float, FailureCategory | None, list[str], list[str], list[str]]:
    result_text = (execution_result or "").lower()
    if not success:
        return "not_satisfied", 0.9, "action_failed", [], ["execution_success"], []
    if "timeout" in result_text:
        return "uncertain", 0.6, "validation_timeout", [], ["completion_signal"], []
    if action_type == "navigate":
        if before_url and after_url and before_url == after_url:
            return (
                "not_satisfied",
                0.85,
                "navigation_failed",
                [],
                ["url_changed"],
                ["expected_navigation_but_url_unchanged"],
            )
        return "satisfied", 0.85, None, ["navigation_completed"], [], []
    if "no effect" in result_text or "unchanged" in result_text:
        return "not_satisfied", 0.8, "unexpected_state", [], ["state_change"], []
    if "partial" in result_text:
        return "not_satisfied", 0.65, "partial_success", ["partial_signal"], ["full_success"], []
    return "satisfied", 0.8, None, ["execution_success"], [], []
