"""
V6.5 Trust Engine — WorkflowTrustAnalyzer.

Evaluates the trustworthiness of a workflow before execution.

Factors:
  + Readiness score (V5.5 intelligence)
  + Workflow tab present (V6.0 tab context)
  - Critical blockers
  - Missing information gaps
  - High-risk workflow type (purchase, send, payment)

Advisory only — never launches or blocks workflows.
"""
from __future__ import annotations

from typing import Optional

from app.trust.models import (
    TrustEvaluation, RiskLevel, TargetType, make_evaluation, max_risk,
)
from app.trust.risk_classifier import classify as classify_risk
from app.trust.approval_advisor import requires_approval as advise_approval
from app.trust import analytics as trust_analytics


class WorkflowTrustAnalyzer:
    """
    Evaluate trust for a workflow about to be executed.

    Combines: workflow type risk + readiness + blockers + tab presence.
    Advisory only.
    """

    def analyze(
        self,
        workflow_type:        str,
        workflow_id:          Optional[str] = None,
        readiness_score:      float = 0.5,
        critical_blocker_count: int = 0,
        missing_info_count:   int   = 0,
        workflow_tab_present: bool  = False,
    ) -> TrustEvaluation:
        """
        Evaluate trust for a workflow.

        Args:
            workflow_type:          e.g. "purchase_workflow", "booking_workflow"
            workflow_id:            optional identifier
            readiness_score:        V5.5 readiness (0.0–1.0)
            critical_blocker_count: number of critical blockers
            missing_info_count:     number of information gaps
            workflow_tab_present:   whether a WORKFLOW-role tab is open (V6.0)

        Returns:
            TrustEvaluation (advisory)
        """
        # Classify risk from workflow type
        # e.g. "purchase_workflow" → classify("purchase_workflow") → CRITICAL
        base_risk = classify_risk(workflow_type)

        # Elevate if blockers exist
        if critical_blocker_count > 0:
            base_risk = max_risk(base_risk, RiskLevel.medium)

        # Compute trust score
        base_scores = {
            RiskLevel.low:      0.90,
            RiskLevel.medium:   0.70,
            RiskLevel.high:     0.50,
            RiskLevel.critical: 0.25,
        }
        score = base_scores[base_risk]
        score += readiness_score * 0.10
        if workflow_tab_present:
            score += 0.05
        score -= min(critical_blocker_count * 0.10, 0.30)
        score -= min(missing_info_count     * 0.05, 0.15)
        score  = max(0.0, min(1.0, score))

        approval  = advise_approval(base_risk)
        confidence = min(1.0, 0.70 + readiness_score * 0.25)

        parts = [f"Workflow '{workflow_type}' risk: {base_risk.value}."]
        parts.append(f"Readiness {readiness_score:.0%}.")
        if critical_blocker_count:
            parts.append(f"{critical_blocker_count} critical blocker(s).")
        if missing_info_count:
            parts.append(f"{missing_info_count} info gap(s).")
        if workflow_tab_present:
            parts.append("Workflow tab open — execution context confirmed.")
        if approval:
            parts.append("User approval recommended before workflow execution.")

        result = make_evaluation(
            target_type       = TargetType.workflow,
            target_id         = workflow_id or workflow_type,
            trust_score       = score,
            risk_level        = base_risk,
            approval_required = approval,
            confidence        = confidence,
            reasoning         = " ".join(parts),
        )
        trust_analytics.record_evaluation(result.risk_level, result.approval_required)
        return result


# Module-level singleton
_analyzer = WorkflowTrustAnalyzer()


def analyze(
    workflow_type:          str,
    workflow_id:            Optional[str] = None,
    readiness_score:        float = 0.5,
    critical_blocker_count: int   = 0,
    missing_info_count:     int   = 0,
    workflow_tab_present:   bool  = False,
) -> TrustEvaluation:
    return _analyzer.analyze(
        workflow_type          = workflow_type,
        workflow_id            = workflow_id,
        readiness_score        = readiness_score,
        critical_blocker_count = critical_blocker_count,
        missing_info_count     = missing_info_count,
        workflow_tab_present   = workflow_tab_present,
    )
