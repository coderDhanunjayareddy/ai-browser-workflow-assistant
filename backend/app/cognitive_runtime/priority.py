from __future__ import annotations

from app.cognitive_runtime.decision_models import CognitiveDecisionType, DecisionSignal
from app.cognitive_runtime.policy import DecisionPolicy


BASE_PRIORITY = {
    CognitiveDecisionType.CANCEL: 100,
    CognitiveDecisionType.FAIL: 95,
    CognitiveDecisionType.REQUEST_USER: 90,
    CognitiveDecisionType.REPLAN: 80,
    CognitiveDecisionType.RECOVER: 70,
    CognitiveDecisionType.WAIT: 65,
    CognitiveDecisionType.COMPLETE_READY: 60,
    CognitiveDecisionType.CONTINUE: 55,
    CognitiveDecisionType.BLOCKED: 50,
    CognitiveDecisionType.UNKNOWN: 10,
}


class PriorityEvaluator:
    """Ranks competing advisory recommendations."""

    def rank(self, signals: list[DecisionSignal], policy: DecisionPolicy) -> list[tuple[DecisionSignal, float, str]]:
        ranked = []
        for signal in signals:
            bias = _bias(signal.decision_type, policy)
            score = BASE_PRIORITY.get(signal.decision_type, 0) * signal.strength * bias
            ranked.append((signal, round(score, 4), f"base_priority={BASE_PRIORITY.get(signal.decision_type, 0)} policy_bias={bias}"))
        return sorted(ranked, key=lambda item: item[1], reverse=True)


def _bias(decision_type: CognitiveDecisionType, policy: DecisionPolicy) -> float:
    if decision_type == CognitiveDecisionType.CONTINUE:
        return policy.continue_bias
    if decision_type == CognitiveDecisionType.WAIT:
        return policy.wait_bias
    if decision_type == CognitiveDecisionType.RECOVER:
        return policy.recovery_bias
    if decision_type == CognitiveDecisionType.REPLAN:
        return policy.replan_bias
    if decision_type == CognitiveDecisionType.REQUEST_USER:
        return policy.user_bias
    if decision_type in {CognitiveDecisionType.FAIL, CognitiveDecisionType.BLOCKED}:
        return policy.fail_bias
    return 1.0
