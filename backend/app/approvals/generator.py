"""
V8.0 Human Approval Center — ApprovalGenerator.

Converts outputs from existing engines into ApprovalRequest objects.
Does NOT duplicate logic from Trust Engine, Decision Center, or Mission Intelligence.
Wraps existing outputs only.

Safety: No execution. No autonomy. No dispatch.
"""
from __future__ import annotations

from app.approvals.models import (
    ApprovalRequest, ApprovalSourceType, ApprovalRiskLevel, make_approval_request,
)


def generate_for_mission(mission_id: str) -> list[ApprovalRequest]:
    """
    Produce ApprovalRequests from all active advisory engines for a mission.
    Each source is wrapped in try/except so a failing engine never blocks the others.
    Returns a flat list; caller is responsible for storing in the registry.
    """
    items: list[ApprovalRequest] = []

    # ── Source 1: Trust Engine (V6.5) ────────────────────────────────────────
    items.extend(_from_trust(mission_id))

    # ── Source 2: Decision Center — CRITICAL open decisions (V7.5) ───────────
    items.extend(_from_decisions(mission_id))

    # ── Source 3: Mission Intelligence — blockers (V5.5) ─────────────────────
    items.extend(_from_mission_intelligence(mission_id))

    return items


# ── Private source adapters ───────────────────────────────────────────────────

def _from_trust(mission_id: str) -> list[ApprovalRequest]:
    out: list[ApprovalRequest] = []
    try:
        from app.trust import mission_analyzer as _ma
        from app.trust.models import RiskLevel

        ev = _ma.analyze(mission_id)

        if ev.risk_level in (RiskLevel.high, RiskLevel.critical):
            rl = (ApprovalRiskLevel.critical
                  if ev.risk_level == RiskLevel.critical
                  else ApprovalRiskLevel.high)
            out.append(make_approval_request(
                source_type  = ApprovalSourceType.trust_engine,
                source_id    = f"trust:mission:{mission_id}",
                title        = f"Trust risk {ev.risk_level.value} — human approval required",
                description  = (
                    f"Mission trust score {round(ev.trust_score, 3)} "
                    f"is {ev.risk_level.value}. {ev.reasoning}"
                ),
                risk_level   = rl,
                priority     = rl.value,
                mission_id   = mission_id,
                metadata     = {
                    "trust_score":       round(ev.trust_score, 3),
                    "risk_level":        ev.risk_level.value,
                    "approval_required": ev.approval_required,
                },
            ))

        if ev.approval_required and ev.risk_level not in (RiskLevel.high, RiskLevel.critical):
            out.append(make_approval_request(
                source_type = ApprovalSourceType.trust_engine,
                source_id   = f"trust:approval_flag:{mission_id}",
                title       = "Trust policy requires explicit approval",
                description = "Trust evaluation flagged approval_required. Review before proceeding.",
                risk_level  = ApprovalRiskLevel.medium,
                priority    = "MEDIUM",
                mission_id  = mission_id,
                metadata    = {"reason": "approval_required"},
            ))
    except Exception:
        pass
    return out


def _from_decisions(mission_id: str) -> list[ApprovalRequest]:
    out: list[ApprovalRequest] = []
    try:
        from app.decisions import registry as dec_reg
        from app.decisions.models import DecisionPriority, DecisionStatus

        all_items = dec_reg.list_for_mission(mission_id, limit=200)
        for item in all_items:
            if (item.priority == DecisionPriority.critical
                    and item.status == DecisionStatus.open):
                out.append(make_approval_request(
                    source_type = ApprovalSourceType.decision_center,
                    source_id   = item.decision_id,
                    title       = f"Critical decision requires human review: {item.title}",
                    description = item.description,
                    risk_level  = ApprovalRiskLevel.critical,
                    priority    = "CRITICAL",
                    mission_id  = mission_id,
                    task_id     = item.task_id,
                    metadata    = {
                        "decision_type": item.decision_type.value,
                        "source":        item.source,
                    },
                ))
    except Exception:
        pass
    return out


def _from_mission_intelligence(mission_id: str) -> list[ApprovalRequest]:
    out: list[ApprovalRequest] = []
    try:
        from app.mission.intelligence import engine as _intel_engine
        from app.mission.intelligence.models import AdvisoryState

        report = _intel_engine.run(mission_id)
        if report is None:
            return out

        for blocker in report.critical_blockers:
            out.append(make_approval_request(
                source_type = ApprovalSourceType.mission_intelligence,
                source_id   = f"blocker:{blocker.code}:{mission_id}",
                title       = f"Mission blocker: {blocker.code}",
                description = blocker.message,
                risk_level  = ApprovalRiskLevel.high,
                priority    = "HIGH",
                mission_id  = mission_id,
                metadata    = {
                    "blocker_code":     blocker.code,
                    "advisory_state":   report.advisory_state.value,
                    "readiness_score":  report.readiness_score,
                },
            ))
    except Exception:
        pass
    return out
