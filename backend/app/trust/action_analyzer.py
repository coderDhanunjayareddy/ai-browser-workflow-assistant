"""
V6.5 Trust Engine — ActionTrustAnalyzer.

Evaluates individual browser actions for trust and risk.
Delegates to RiskClassifier and TrustPolicyEngine.

Actions evaluated:
  click, fill, navigate, submit, send, delete, purchase, etc.

No execution. Advisory only.
"""
from __future__ import annotations

from typing import Optional

from app.trust.models import TrustEvaluation, TargetType
from app.trust.policy_engine import TrustPolicyEngine
from app.trust import analytics as trust_analytics


class ActionTrustAnalyzer:
    """
    Evaluate a single browser action for trust.

    Returns TrustEvaluation with risk_level and approval_required.
    Never executes the action. Advisory only.
    """

    def __init__(self) -> None:
        self._engine = TrustPolicyEngine()

    def analyze(
        self,
        action_type:     str,
        action_id:       Optional[str] = None,
        workflow_type:   Optional[str] = None,
        readiness_score: float = 0.5,
        blocker_count:   int   = 0,
    ) -> TrustEvaluation:
        """
        Evaluate trust for an action.

        Args:
            action_type:     e.g. "click", "purchase", "delete"
            action_id:       optional identifier for this specific action
            workflow_type:   optional workflow context
            readiness_score: V5.5 mission readiness (0.0–1.0)
            blocker_count:   number of active critical blockers

        Returns:
            TrustEvaluation (advisory — never executes)
        """
        result = self._engine.evaluate(
            action_type     = action_type,
            target_type     = TargetType.action,
            target_id       = action_id or action_type,
            workflow_type   = workflow_type,
            readiness_score = readiness_score,
            blocker_count   = blocker_count,
        )
        trust_analytics.record_evaluation(result.risk_level, result.approval_required)
        return result


# Module-level singleton
_analyzer = ActionTrustAnalyzer()


def analyze(
    action_type:     str,
    action_id:       Optional[str] = None,
    workflow_type:   Optional[str] = None,
    readiness_score: float = 0.5,
    blocker_count:   int   = 0,
) -> TrustEvaluation:
    return _analyzer.analyze(
        action_type     = action_type,
        action_id       = action_id,
        workflow_type   = workflow_type,
        readiness_score = readiness_score,
        blocker_count   = blocker_count,
    )
