from __future__ import annotations

from typing import Any

from app.cognitive_runtime.decision_models import CognitiveDecisionType, DecisionSignal


class DeclarativeDecisionRuleSet:
    """Workflow-agnostic advisory rules for cognitive decisions."""

    def evaluate(
        self,
        *,
        readiness: Any | None,
        diagnostics: Any | None,
        wait_state: Any | None,
        clarification: Any | None,
        recovery: Any | None,
        replanning: Any | None,
        progress: Any | None,
    ) -> list[DecisionSignal]:
        signals: list[DecisionSignal] = []
        if getattr(clarification, "required_count", 0):
            signals.append(DecisionSignal(CognitiveDecisionType.REQUEST_USER, 0.95, "required_clarification_unanswered"))
        if getattr(wait_state, "waiting", False):
            signals.append(DecisionSignal(CognitiveDecisionType.WAIT, 0.85, f"active_wait:{getattr(wait_state, 'primary_wait', None)}"))
        if getattr(recovery, "classification", "unknown") in {"recoverable", "partially_recoverable"}:
            signals.append(DecisionSignal(CognitiveDecisionType.RECOVER, 0.8, f"recovery_{recovery.classification}"))
        if getattr(replanning, "recommendation", "unnecessary") == "required":
            signals.append(DecisionSignal(CognitiveDecisionType.REPLAN, 0.95, "replanning_required"))
        elif getattr(replanning, "recommendation", "unnecessary") == "recommended":
            signals.append(DecisionSignal(CognitiveDecisionType.REPLAN, 0.65, "replanning_recommended"))
        if list(getattr(diagnostics, "contradictions", []) or []):
            signals.append(DecisionSignal(CognitiveDecisionType.REPLAN, 0.75, "contradictions_present"))
        if list(getattr(readiness, "ready_nodes", []) or []):
            signals.append(DecisionSignal(CognitiveDecisionType.CONTINUE, 0.75, "ready_nodes_available"))
        if float(getattr(progress, "completion_percentage", 0.0) or 0.0) >= 1.0:
            signals.append(DecisionSignal(CognitiveDecisionType.COMPLETE_READY, 0.9, "all_nodes_completed"))
        if list(getattr(readiness, "blocked_nodes", []) or []) and not signals:
            signals.append(DecisionSignal(CognitiveDecisionType.BLOCKED, 0.8, "blocked_nodes_without_recovery"))
        if getattr(recovery, "classification", "") == "blocked":
            signals.append(DecisionSignal(CognitiveDecisionType.BLOCKED, 0.85, "recovery_blocked"))
        if not signals:
            signals.append(DecisionSignal(CognitiveDecisionType.UNKNOWN, 0.3, "insufficient_decision_signal"))
        return signals
