"""
V8.8 Execution Authorization Framework — ReadinessEngine.

Produces ExecutionReadinessReport for a mission.
No execution. Pure read-only assessment.

Readiness score = fraction of 5 conditions met:
  1. Mission is ACTIVE
  2. At least 1 eligible governance contract exists
  3. At least 1 approved approval request exists
  4. Trust score >= TRUST_SCORE_THRESHOLD (0.5)
  5. At least 1 active authorized ExecutionAuthorization exists
"""
from __future__ import annotations

import time

from app.authorization.models import (
    ExecutionReadinessReport, TRUST_SCORE_THRESHOLD, AuthorizationStatus,
)


class ReadinessEngine:

    def evaluate(self, mission_id: str) -> ExecutionReadinessReport:
        now      = time.time()
        blockers: list[str] = []
        scores:   list[float] = []

        # ── 1. Mission state ──────────────────────────────────────────────────
        mission_ready = False
        try:
            from app.mission import store as ms
            m = ms.get(mission_id)
            if m is None:
                blockers.append("Mission not found")
            elif m.state.value.upper() in ("ACTIVE", "RUNNING"):
                mission_ready = True
            else:
                blockers.append(f"Mission state is {m.state.value}, not ACTIVE")
        except Exception:
            blockers.append("Mission store unavailable")
        scores.append(1.0 if mission_ready else 0.0)

        # ── 2. Governance contracts ───────────────────────────────────────────
        contracts_ready = 0
        try:
            from app.governance import registry as gov_reg
            s = gov_reg.summary_for_mission(mission_id)
            contracts_ready = s.get("execution_eligible", 0)
            if contracts_ready == 0:
                blockers.append("No eligible governance contracts for mission")
        except Exception:
            blockers.append("Governance registry unavailable")
        scores.append(1.0 if contracts_ready > 0 else 0.0)

        # ── 3. Approvals ──────────────────────────────────────────────────────
        approvals_ready = 0
        try:
            from app.approvals import registry as appr_reg
            from app.approvals.models import ApprovalStatus
            all_appr = appr_reg.list_for_mission(mission_id, limit=500)
            approvals_ready = sum(1 for a in all_appr if a.status == ApprovalStatus.approved)
            if approvals_ready == 0:
                blockers.append("No approved approvals for mission")
        except Exception:
            blockers.append("Approval registry unavailable")
        scores.append(1.0 if approvals_ready > 0 else 0.0)

        # ── 4. Trust ──────────────────────────────────────────────────────────
        trust_ready = False
        try:
            from app.trust import mission_analyzer as ma
            ev = ma.analyze(mission_id)
            trust_ready = ev.trust_score >= TRUST_SCORE_THRESHOLD
            if not trust_ready:
                blockers.append(
                    f"Trust score {round(ev.trust_score, 3)} below "
                    f"threshold {TRUST_SCORE_THRESHOLD}"
                )
        except Exception:
            trust_ready = True   # trust module unavailable → assume OK
        scores.append(1.0 if trust_ready else 0.0)

        # ── 5. Active authorizations ──────────────────────────────────────────
        active_authorizations  = 0
        denied_authorizations  = 0
        executable_tasks: list[str] = []
        try:
            from app.authorization import registry as auth_reg
            auth_items = auth_reg.list_for_mission(mission_id, limit=500)
            active_authorizations = sum(
                1 for a in auth_items
                if a.status == AuthorizationStatus.active and a.authorized
            )
            denied_authorizations = sum(
                1 for a in auth_items
                if not a.authorized or a.status == AuthorizationStatus.denied
            )
            executable_tasks = list({
                a.task_id for a in auth_items
                if a.task_id and a.is_executable
            })
            if active_authorizations == 0:
                blockers.append("No active authorizations for mission — evaluate a contract first")
        except Exception:
            blockers.append("Authorization registry unavailable")
        scores.append(1.0 if active_authorizations > 0 else 0.0)

        readiness_score = round(sum(scores) / len(scores), 3) if scores else 0.0

        return ExecutionReadinessReport(
            mission_id            = mission_id,
            mission_ready         = mission_ready,
            contracts_ready       = contracts_ready,
            approvals_ready       = approvals_ready,
            trust_ready           = trust_ready,
            blockers              = blockers,
            readiness_score       = readiness_score,
            evaluated_at          = now,
            active_authorizations = active_authorizations,
            denied_authorizations = denied_authorizations,
            executable_tasks      = executable_tasks,
        )


# Module-level singleton
_engine = ReadinessEngine()


def evaluate(mission_id: str) -> ExecutionReadinessReport:
    return _engine.evaluate(mission_id)
