"""
V7.5 Decision Center — PriorityEngine.

Deterministic priority scoring from 0-100.
No LLM. No ML. Pure rule-based scoring.

Priority thresholds:
  CRITICAL >= 90
  HIGH     >= 60
  MEDIUM   >= 30
  LOW      <  30
"""
from __future__ import annotations

from app.decisions.models import DecisionPriority

_CRITICAL_THRESHOLD = 90
_HIGH_THRESHOLD     = 60
_MEDIUM_THRESHOLD   = 30


class PriorityEngine:
    """
    Scores a potential decision based on contributing signals.
    All inputs are optional; omitted signals contribute 0.
    """

    def score(
        self,
        *,
        trust_risk_level: str  = "LOW",
        has_blocker:      bool = False,
        mission_readiness: float = 1.0,
        confidence:       float = 0.5,
        decision_type:    str  = "INFO",
    ) -> int:
        s = 0

        # Trust risk contribution (0-50)
        _trust_weights = {"CRITICAL": 50, "HIGH": 40, "MEDIUM": 20, "LOW": 0}
        s += _trust_weights.get(trust_risk_level.upper(), 0)

        # Blocker contribution (0-30)
        if has_blocker:
            s += 30

        # Low mission readiness contribution (0-20)
        if mission_readiness < 0.30:
            s += 20
        elif mission_readiness < 0.50:
            s += 10
        elif mission_readiness < 0.70:
            s += 5

        # Decision type boost
        _type_boost = {
            "TRUST_WARNING": 10,
            "BLOCKER":       10,
            "RECOMMENDATION": 5,
            "OPPORTUNITY":    3,
            "INFO":           0,
        }
        s += _type_boost.get(decision_type.upper(), 0)

        # Confidence factor (scale down low-confidence signals)
        s = int(s * max(0.3, confidence))

        return min(100, s)

    def priority_from_score(self, score: int) -> DecisionPriority:
        if score >= _CRITICAL_THRESHOLD:
            return DecisionPriority.critical
        if score >= _HIGH_THRESHOLD:
            return DecisionPriority.high
        if score >= _MEDIUM_THRESHOLD:
            return DecisionPriority.medium
        return DecisionPriority.low

    def classify(
        self,
        *,
        trust_risk_level: str  = "LOW",
        has_blocker:      bool = False,
        mission_readiness: float = 1.0,
        confidence:       float = 0.5,
        decision_type:    str  = "INFO",
    ) -> DecisionPriority:
        return self.priority_from_score(self.score(
            trust_risk_level  = trust_risk_level,
            has_blocker       = has_blocker,
            mission_readiness = mission_readiness,
            confidence        = confidence,
            decision_type     = decision_type,
        ))


# Module-level singleton
_engine = PriorityEngine()


def classify(**kwargs) -> DecisionPriority:
    return _engine.classify(**kwargs)

def score(**kwargs) -> int:
    return _engine.score(**kwargs)
