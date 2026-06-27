"""
Phase B — Execution Gateway V1 — ExecutionGateway.

The single runtime responsible for executing an approved ExecutionPlan. It is an
ORCHESTRATION engine: it verifies the upstream chain, creates an ExecutionRecord,
and runs the plan through the dispatcher + adapter. It never touches a browser.

Preflight verification (reuses existing layers, no redesign):
  HARD (must pass to start):
    - plan exists and status == READY
    - authorization exists and is_executable
    - mission active (when the plan has a mission)
  SOFT (recorded, non-blocking):
    - governance contract present
    - approval present
    - runtime session present
    - browser sync present
"""
from __future__ import annotations

import time
from typing import Any, Optional

from app.execution_gateway import analytics as gw_analytics
from app.execution_gateway import audit as audit_trail
from app.execution_gateway import registry as exec_registry
from app.execution_gateway import rollback_engine
from app.execution_gateway import runner as exec_runner
from app.execution_gateway import timeline as gw_timeline
from app.execution_gateway.adapter import ExecutionAdapter
from app.execution_gateway.mock_adapter import MockBrowserAdapter
from app.execution_gateway.models import (
    ExecutionRecord,
    ExecutionState,
    RetryConfig,
    StepOutcome,
    make_audit_entry,
    make_execution,
)
from app.execution_planning.models import PlanStatus


class GatewayError(Exception):
    """Raised when an execution cannot start or a control action is invalid."""
    def __init__(self, message: str, *, status_code: int = 400, preflight: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.preflight = preflight or {}


class ExecutionGateway:

    # ── preflight ──────────────────────────────────────────────────────────────

    def preflight(self, plan) -> dict[str, Any]:
        """Verify the upstream chain. Returns a structured preflight report."""
        checks: dict[str, bool] = {}
        reasons: list[str] = []

        # HARD: plan READY
        plan_ready = plan is not None and plan.status == PlanStatus.ready
        checks["plan_ready"] = plan_ready
        if not plan_ready:
            reasons.append("plan is not READY")

        # HARD: authorization executable
        auth_ok = False
        try:
            from app.authorization import registry as auth_reg
            auth = auth_reg.get(plan.authorization_id) if plan else None
            auth_ok = auth is not None and auth.is_executable
            if not auth_ok:
                reasons.append("authorization missing or not executable")
        except Exception:
            reasons.append("authorization lookup failed")
        checks["authorization_valid"] = auth_ok

        # HARD: mission active (only when plan carries a mission)
        mission_ok = True
        if plan and plan.mission_id:
            mission_ok = False
            try:
                from app.mission import store as ms
                from app.mission.models import MissionState
                m = ms.get(plan.mission_id)
                mission_ok = m is not None and m.state == MissionState.active
                if not mission_ok:
                    reasons.append("mission missing or not active")
            except Exception:
                reasons.append("mission lookup failed")
        checks["mission_active"] = mission_ok

        # SOFT: governance present
        try:
            from app.governance import registry as gov_reg
            gov = gov_reg.summary_for_mission(plan.mission_id) if (plan and plan.mission_id) else None
            checks["governance_present"] = bool(gov and gov.get("total", gov.get("active", 0)))
        except Exception:
            checks["governance_present"] = False

        # SOFT: approval present
        try:
            from app.approvals import queue as appr_queue
            ap = appr_queue.summary_for_mission(plan.mission_id) if (plan and plan.mission_id) else None
            checks["approval_present"] = bool(ap)
        except Exception:
            checks["approval_present"] = False

        # SOFT: runtime present
        try:
            from app.runtime import registry as rt_reg
            sessions = rt_reg.list_for_mission(plan.mission_id, limit=1) if (plan and plan.mission_id) else []
            checks["runtime_present"] = len(sessions) > 0
        except Exception:
            checks["runtime_present"] = False

        # SOFT: browser sync present
        try:
            from app.browser import registry as browser_reg
            evs = browser_reg.events_for_mission(plan.mission_id, limit=1) if (plan and plan.mission_id) else []
            checks["browser_sync_present"] = len(evs) > 0
        except Exception:
            checks["browser_sync_present"] = False

        hard_ok = checks["plan_ready"] and checks["authorization_valid"] and checks["mission_active"]
        return {
            "passed":  hard_ok,
            "checks":  checks,
            "reasons": reasons,
            "evaluated_at": time.time(),
        }

    # ── start ──────────────────────────────────────────────────────────────────

    def start(
        self,
        plan_id: str,
        *,
        adapter:      Optional[ExecutionAdapter] = None,
        auto_run:     bool = True,
        retry_config: Optional[RetryConfig] = None,
    ) -> ExecutionRecord:
        from app.execution_planning import registry as plan_reg
        plan = plan_reg.get(plan_id)
        if plan is None:
            raise GatewayError(f"Plan {plan_id} not found", status_code=404)

        report = self.preflight(plan)
        if not report["passed"]:
            raise GatewayError(
                f"Preflight failed: {', '.join(report['reasons'])}",
                status_code=409, preflight=report,
            )

        adapter = adapter or MockBrowserAdapter()
        record = make_execution(
            plan_id          = plan.plan_id,
            authorization_id = plan.authorization_id,
            mission_id       = plan.mission_id,
            task_id          = plan.task_id,
            total_steps      = len(plan.steps),
            adapter_name     = adapter.name,
            created_at       = time.time(),
            retry_config     = retry_config,
            metadata         = {"execution_mode": plan.execution_mode.value},
        )
        record.preflight = report
        exec_registry.add(record)
        gw_analytics.record_started()
        gw_timeline.record(record.execution_id, "started",
                           mission_id=record.mission_id or "", plan_id=plan.plan_id,
                           state=record.state.value)

        if auto_run:
            self._run_to_completion(record, plan, adapter)
        return record

    # ── lifecycle control ──────────────────────────────────────────────────────

    def pause(self, execution_id: str) -> ExecutionRecord:
        record = self._require(execution_id)
        if record.state not in (ExecutionState.pending, ExecutionState.running):
            raise GatewayError(
                f"Cannot pause execution in state {record.state.value}",
                status_code=409,
            )
        record.state = ExecutionState.paused
        record.updated_at = time.time()
        gw_timeline.record(execution_id, "paused", mission_id=record.mission_id or "",
                           plan_id=record.plan_id, state=record.state.value)
        return record

    def resume(self, execution_id: str, adapter: Optional[ExecutionAdapter] = None) -> ExecutionRecord:
        record = self._require(execution_id)
        if record.state not in (ExecutionState.paused, ExecutionState.pending):
            raise GatewayError(
                f"Cannot resume execution in state {record.state.value}",
                status_code=409,
            )
        from app.execution_planning import registry as plan_reg
        plan = plan_reg.get(record.plan_id)
        if plan is None:
            raise GatewayError(f"Plan {record.plan_id} no longer available", status_code=409)
        gw_timeline.record(execution_id, "resumed", mission_id=record.mission_id or "",
                           plan_id=record.plan_id, state="RUNNING")
        adapter = adapter or MockBrowserAdapter()
        self._run_to_completion(record, plan, adapter)
        return record

    def abort(self, execution_id: str) -> ExecutionRecord:
        record = self._require(execution_id)
        if record.is_terminal:
            raise GatewayError(
                f"Cannot abort execution in terminal state {record.state.value}",
                status_code=409,
            )
        # Simulate rollback of any completed steps.
        completed = [s for s in record.step_executions if s.outcome == StepOutcome.success]
        report = rollback_engine.simulate(completed)
        record.rollback_history = report
        record.state = ExecutionState.aborted
        record.finished_at = time.time()
        record.updated_at  = record.finished_at
        audit_trail.append(make_audit_entry(
            execution_id      = execution_id,
            step_id           = "",
            order             = record.current_step_index,
            command_type      = "ABORT",
            timestamp         = time.time(),
            duration_ms       = 0.0,
            outcome           = "ABORTED",
            validation_passed = False,
            retry_count       = 0,
            rollback_performed= bool(report),
            message           = f"aborted; rolled back {len(report)} step(s)",
        ))
        gw_timeline.record(execution_id, "aborted", mission_id=record.mission_id or "",
                           plan_id=record.plan_id, state=record.state.value)
        if report:
            gw_timeline.record(execution_id, "rolled_back", mission_id=record.mission_id or "",
                               plan_id=record.plan_id, state=record.state.value)
        self._record_finished(record)
        return record

    # ── internals ──────────────────────────────────────────────────────────────

    def _run_to_completion(self, record: ExecutionRecord, plan, adapter: ExecutionAdapter) -> None:
        exec_runner.run(record, plan, adapter)
        event = {
            ExecutionState.completed: "completed",
            ExecutionState.failed:    "failed",
        }.get(record.state)
        if event:
            gw_timeline.record(record.execution_id, event,
                               mission_id=record.mission_id or "", plan_id=record.plan_id,
                               state=record.state.value)
            if record.state == ExecutionState.failed and record.rollback_history:
                gw_timeline.record(record.execution_id, "rolled_back",
                                   mission_id=record.mission_id or "", plan_id=record.plan_id,
                                   state=record.state.value)
        self._record_finished(record)

    def _record_finished(self, record: ExecutionRecord) -> None:
        gw_analytics.record_finished(
            state          = record.state.value,
            steps_executed = record.completed_steps + record.failed_steps,
            steps_failed   = record.failed_steps,
            retries        = record.total_retries,
            rollbacks      = len(record.rollback_history),
            duration_ms    = record.total_duration_ms,
        )

    def _require(self, execution_id: str) -> ExecutionRecord:
        record = exec_registry.get(execution_id)
        if record is None:
            raise GatewayError(f"Execution {execution_id} not found", status_code=404)
        return record


# ── Module-level singleton ────────────────────────────────────────────────────

_gateway = ExecutionGateway()


def preflight(plan) -> dict:                              return _gateway.preflight(plan)
def start(plan_id: str, **kwargs) -> ExecutionRecord:    return _gateway.start(plan_id, **kwargs)
def pause(execution_id: str) -> ExecutionRecord:         return _gateway.pause(execution_id)
def resume(execution_id: str, adapter=None) -> ExecutionRecord: return _gateway.resume(execution_id, adapter)
def abort(execution_id: str) -> ExecutionRecord:         return _gateway.abort(execution_id)
