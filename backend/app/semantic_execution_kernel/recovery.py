from __future__ import annotations

from app.semantic_execution_kernel.models import EligibilityResult, RecoveryDecision


def recovery_decision(eligibility: EligibilityResult | None) -> RecoveryDecision:
    if eligibility is None or eligibility.eligible:
        return RecoveryDecision("none", "proposal is eligible")
    failures = set(eligibility.failures)
    if "entity_missing" in failures:
        return RecoveryDecision("reextract_entities", "entity is missing from registry")
    if "selector_binding_missing" in failures:
        return RecoveryDecision("resolve_entity_again", "entity lacks executable selector binding")
    if "entity_has_no_url_or_selector" in failures:
        return RecoveryDecision("fallback_capability", "entity lacks direct browser binding")
    if "loop_detected" in failures:
        return RecoveryDecision("skip_entity", "proposal repeats previous progress")
    if "retry_budget_exceeded" in failures or "mission_blocked" in failures:
        return RecoveryDecision("escalate", "mission retry budget exceeded")
    return RecoveryDecision("refresh", eligibility.reason)
