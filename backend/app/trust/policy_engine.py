"""
V6.5 Trust Engine — TrustPolicyEngine.

Rule-based policy evaluation that combines risk classification,
mission context, and tab state into a final TrustEvaluation.

No LLM. No embeddings. Pure deterministic rules.
Advisory only — never executes, never approves automatically.
"""
from __future__ import annotations

from typing import Optional

from app.trust.models import (
    TrustEvaluation, RiskLevel, TargetType,
    make_evaluation, max_risk,
)
from app.trust.risk_classifier import classify as classify_risk
from app.trust.approval_advisor import ApprovalAdvisorV2


class TrustPolicyEngine:
    """
    Combines all trust signals into a final TrustEvaluation.

    Inputs accepted:
      action_type     — the action being evaluated
      workflow_type   — optional workflow context
      tab_role        — optional tab role hint
      readiness_score — optional V5.5 mission readiness (0.0–1.0)
      blocker_count   — number of active critical blockers
      missing_info_count — number of information gaps
      target_type     — MISSION / TASK / WORKFLOW / TAB / ACTION
      target_id       — identifier for the target

    All inputs are optional beyond action_type. Missing inputs are treated
    as neutral (no deduction / no bonus).
    """

    def __init__(self) -> None:
        self._advisor = ApprovalAdvisorV2()

    def evaluate(
        self,
        action_type:        str,
        target_type:        TargetType = TargetType.action,
        target_id:          str        = "unknown",
        workflow_type:      Optional[str] = None,
        tab_role:           Optional[str] = None,
        readiness_score:    float = 0.5,
        blocker_count:      int   = 0,
        missing_info_count: int   = 0,
    ) -> TrustEvaluation:
        """
        Evaluate trust for any platform target.

        Returns a TrustEvaluation (advisory — never mutates state).
        """
        # Step 1: classify base risk from action type
        base_risk = classify_risk(action_type)

        # Step 2: elevate risk based on context signals
        elevated_risk = self._elevate_risk(
            base_risk, workflow_type, tab_role, blocker_count,
        )

        # Step 3: compute trust score
        trust_score = self._compute_score(
            elevated_risk, readiness_score, blocker_count, missing_info_count,
        )

        # Step 4: approval recommendation
        approval = self._advisor.requires_approval(elevated_risk)
        confidence = self._compute_confidence(readiness_score, blocker_count)

        # Step 5: build reasoning
        parts: list[str] = [
            f"Action '{action_type}' classified as {elevated_risk.value} risk.",
        ]
        if blocker_count > 0:
            parts.append(f"{blocker_count} active blocker(s) reduce trust.")
        if missing_info_count > 0:
            parts.append(f"{missing_info_count} information gap(s) detected.")
        if approval:
            parts.append("User approval recommended before execution.")
        else:
            parts.append("No approval required for this risk level.")
        reasoning = " ".join(parts)

        return make_evaluation(
            target_type       = target_type,
            target_id         = target_id,
            trust_score       = trust_score,
            risk_level        = elevated_risk,
            approval_required = approval,
            confidence        = confidence,
            reasoning         = reasoning,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _elevate_risk(
        self,
        base: RiskLevel,
        workflow_type: Optional[str],
        tab_role:      Optional[str],
        blocker_count: int,
    ) -> RiskLevel:
        """Elevate risk based on context signals, never decrease it."""
        risk = base

        # Workflow-type hints
        if workflow_type:
            wf = workflow_type.lower()
            if any(k in wf for k in ("purchase", "payment", "checkout")):
                risk = max_risk(risk, RiskLevel.critical)
            elif any(k in wf for k in ("send", "email", "message")):
                risk = max_risk(risk, RiskLevel.high)
            elif any(k in wf for k in ("booking", "submit", "order")):
                risk = max_risk(risk, RiskLevel.high)

        # Orphan tab (no mission context) raises risk
        if tab_role == "ORPHAN":
            risk = max_risk(risk, RiskLevel.medium)

        # Critical blockers raise minimum risk to MEDIUM
        if blocker_count > 0:
            risk = max_risk(risk, RiskLevel.medium)

        return risk

    def _compute_score(
        self,
        risk:               RiskLevel,
        readiness_score:    float,
        blocker_count:      int,
        missing_info_count: int,
    ) -> float:
        """Compute trust score (0.0–1.0) from risk and context."""
        # Base score by risk level
        base_scores = {
            RiskLevel.low:      0.95,
            RiskLevel.medium:   0.75,
            RiskLevel.high:     0.50,
            RiskLevel.critical: 0.20,
        }
        score = base_scores[risk]

        # Readiness bonus (max +0.05 for fully ready missions)
        score += readiness_score * 0.05

        # Blocker deductions
        score -= min(blocker_count * 0.10, 0.30)

        # Missing info deductions
        score -= min(missing_info_count * 0.05, 0.15)

        return max(0.0, min(1.0, score))

    def _compute_confidence(
        self,
        readiness_score: float,
        blocker_count:   int,
    ) -> float:
        """Confidence in this evaluation (0.0–1.0)."""
        base = 0.80
        base += readiness_score * 0.15
        base -= min(blocker_count * 0.10, 0.30)
        return max(0.30, min(1.0, base))


# Module-level singleton
_engine = TrustPolicyEngine()


def evaluate(
    action_type:        str,
    target_type:        TargetType = TargetType.action,
    target_id:          str        = "unknown",
    workflow_type:      Optional[str] = None,
    tab_role:           Optional[str] = None,
    readiness_score:    float = 0.5,
    blocker_count:      int   = 0,
    missing_info_count: int   = 0,
) -> TrustEvaluation:
    return _engine.evaluate(
        action_type        = action_type,
        target_type        = target_type,
        target_id          = target_id,
        workflow_type      = workflow_type,
        tab_role           = tab_role,
        readiness_score    = readiness_score,
        blocker_count      = blocker_count,
        missing_info_count = missing_info_count,
    )
