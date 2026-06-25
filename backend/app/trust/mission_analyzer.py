"""
V6.5 Trust Engine — MissionTrustAnalyzer.

Evaluates overall mission trust by aggregating:
  - V5.5 Mission Intelligence (readiness, blockers, information gaps)
  - V6.0 Tab Context (tab count, roles, orphan tabs)
  - Task states (completed/failed ratio)

Advisory only. Never mutates mission state.
"""
from __future__ import annotations

from typing import Optional

from app.trust.models import (
    TrustEvaluation, RiskLevel, TargetType, make_evaluation,
)
from app.trust.approval_advisor import requires_approval as advise_approval
from app.trust import analytics as trust_analytics


class MissionTrustAnalyzer:
    """
    Produce a mission-level TrustEvaluation.

    Consumes intelligence report and tab context as plain dicts to avoid
    circular imports and keep the trust layer loosely coupled.
    """

    def analyze(
        self,
        mission_id:          str,
        readiness_score:     float = 0.0,
        critical_blockers:   int   = 0,
        missing_info_count:  int   = 0,
        task_count:          int   = 0,
        completed_task_count: int  = 0,
        failed_task_count:   int   = 0,
        tab_count:           int   = 0,
        orphan_tab_count:    int   = 0,
        workflow_tab_present: bool = False,
    ) -> TrustEvaluation:
        """
        Evaluate mission-level trust.

        High trust conditions:
          - completed research tasks
          - readiness_score >= 0.80
          - low/zero critical blockers
          - tabs linked to mission (not orphans)

        Low trust conditions:
          - failed tasks
          - orphan tabs
          - missing information
          - zero tasks
        """
        reasons: list[str] = []
        score = 0.50  # neutral start

        # --- Readiness contribution (up to +0.30) ---
        score += readiness_score * 0.30
        reasons.append(f"Readiness {readiness_score:.0%}.")

        # --- Task completion contribution ---
        if task_count > 0:
            completion_ratio = completed_task_count / task_count
            score += completion_ratio * 0.20
            reasons.append(
                f"{completed_task_count}/{task_count} tasks completed."
            )
            if failed_task_count > 0:
                score -= failed_task_count * 0.08
                reasons.append(f"{failed_task_count} failed task(s) reduce trust.")
        else:
            score -= 0.10
            reasons.append("No tasks — insufficient context.")

        # --- Blocker deductions ---
        if critical_blockers > 0:
            score -= min(critical_blockers * 0.10, 0.25)
            reasons.append(f"{critical_blockers} critical blocker(s).")

        # --- Missing info deductions ---
        if missing_info_count > 0:
            score -= min(missing_info_count * 0.05, 0.15)
            reasons.append(f"{missing_info_count} information gap(s).")

        # --- Tab signals ---
        if tab_count > 0:
            if workflow_tab_present:
                score += 0.05
                reasons.append("Workflow tab present.")
            if orphan_tab_count > 0:
                score -= orphan_tab_count * 0.05
                reasons.append(f"{orphan_tab_count} orphan tab(s) not linked to mission.")
        else:
            reasons.append("No tabs registered for this mission.")

        score = max(0.0, min(1.0, score))

        # Risk level from score
        if score >= 0.75:
            risk = RiskLevel.low
        elif score >= 0.55:
            risk = RiskLevel.medium
        elif score >= 0.35:
            risk = RiskLevel.high
        else:
            risk = RiskLevel.critical

        # Ensure critical blockers elevate risk
        if critical_blockers >= 2:
            if risk == RiskLevel.low:
                risk = RiskLevel.medium

        approval   = advise_approval(risk)
        confidence = min(1.0, 0.60 + readiness_score * 0.35)

        if approval:
            reasons.append("User review recommended before execution.")

        result = make_evaluation(
            target_type       = TargetType.mission,
            target_id         = mission_id,
            trust_score       = score,
            risk_level        = risk,
            approval_required = approval,
            confidence        = confidence,
            reasoning         = " ".join(reasons),
        )
        trust_analytics.record_evaluation(result.risk_level, result.approval_required)
        return result


# Module-level singleton
_analyzer = MissionTrustAnalyzer()


def analyze(
    mission_id:           str,
    readiness_score:      float = 0.0,
    critical_blockers:    int   = 0,
    missing_info_count:   int   = 0,
    task_count:           int   = 0,
    completed_task_count: int   = 0,
    failed_task_count:    int   = 0,
    tab_count:            int   = 0,
    orphan_tab_count:     int   = 0,
    workflow_tab_present: bool  = False,
) -> TrustEvaluation:
    return _analyzer.analyze(
        mission_id            = mission_id,
        readiness_score       = readiness_score,
        critical_blockers     = critical_blockers,
        missing_info_count    = missing_info_count,
        task_count            = task_count,
        completed_task_count  = completed_task_count,
        failed_task_count     = failed_task_count,
        tab_count             = tab_count,
        orphan_tab_count      = orphan_tab_count,
        workflow_tab_present  = workflow_tab_present,
    )
