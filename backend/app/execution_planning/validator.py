"""
V9.0 Execution Planning Layer — PlanValidator.

Verifies an ExecutionPlan is well-formed and safe to mark READY for the future
Execution Gateway. Performs NO execution.

Checks (all must pass for valid=True):
  authorization_valid  — the plan's ExecutionAuthorization exists and is executable
  mission_active       — the mission exists and is ACTIVE (skipped if no mission_id)
  task_exists          — the task is attached to the mission (skipped if no task_id)
  no_missing_params    — every step is well-formed (target + required params)
  rollback_defined     — every mutating step has a rollback action
  execution_mode_valid — the plan's execution_mode is a known mode

External reads (authorization / mission) are non-blocking: a lookup failure
produces a FAILED check, never an exception.
"""
from __future__ import annotations

import time
from typing import Optional

from app.execution_planning.models import (
    ActionType,
    ExecutionPlan,
    PlanValidationResult,
    VALID_EXECUTION_MODES,
)


class PlanValidator:

    def validate(self, plan: ExecutionPlan) -> PlanValidationResult:
        checks: dict[str, bool] = {}
        errors: list[str] = []

        # 1. authorization valid
        auth_ok, auth_err = self._check_authorization(plan)
        checks["authorization_valid"] = auth_ok
        if not auth_ok:
            errors.append(auth_err)

        # 2. mission active (skipped → True if plan has no mission_id)
        mission_ok, mission_err = self._check_mission(plan)
        checks["mission_active"] = mission_ok
        if not mission_ok:
            errors.append(mission_err)

        # 3. task exists (skipped → True if plan has no task_id)
        task_ok, task_err = self._check_task(plan)
        checks["task_exists"] = task_ok
        if not task_ok:
            errors.append(task_err)

        # 4. no missing parameters
        params_ok, params_err = self._check_parameters(plan)
        checks["no_missing_parameters"] = params_ok
        if not params_ok:
            errors.append(params_err)

        # 5. rollback defined when required
        rollback_ok, rollback_err = self._check_rollback(plan)
        checks["rollback_defined"] = rollback_ok
        if not rollback_ok:
            errors.append(rollback_err)

        # 6. execution mode valid
        mode_ok = plan.execution_mode in VALID_EXECUTION_MODES
        checks["execution_mode_valid"] = mode_ok
        if not mode_ok:
            errors.append(f"unknown execution_mode: {plan.execution_mode}")

        # 7. plan has at least one step
        has_steps = len(plan.steps) > 0
        checks["has_steps"] = has_steps
        if not has_steps:
            errors.append("plan has no steps")

        valid = all(checks.values())
        return PlanValidationResult(
            plan_id      = plan.plan_id,
            valid        = valid,
            checks       = checks,
            errors       = errors,
            validated_at = time.time(),
        )

    # ── individual checks ──────────────────────────────────────────────────────

    @staticmethod
    def _check_authorization(plan: ExecutionPlan) -> tuple[bool, str]:
        try:
            from app.authorization import registry as auth_reg
            auth_obj = auth_reg.get(plan.authorization_id)
            if auth_obj is None:
                return False, f"authorization {plan.authorization_id} not found"
            if not auth_obj.is_executable:
                return False, f"authorization {plan.authorization_id} is not executable (status={auth_obj.status.value})"
            return True, ""
        except Exception as e:   # pragma: no cover - defensive
            return False, f"authorization lookup failed: {e}"

    @staticmethod
    def _check_mission(plan: ExecutionPlan) -> tuple[bool, str]:
        if not plan.mission_id:
            return True, ""
        try:
            from app.mission import store as ms
            from app.mission.models import MissionState
            m = ms.get(plan.mission_id)
            if m is None:
                return False, f"mission {plan.mission_id} not found"
            if m.state != MissionState.active:
                return False, f"mission {plan.mission_id} not active (state={m.state.value})"
            return True, ""
        except Exception as e:   # pragma: no cover - defensive
            return False, f"mission lookup failed: {e}"

    @staticmethod
    def _check_task(plan: ExecutionPlan) -> tuple[bool, str]:
        if not plan.task_id:
            return True, ""
        try:
            from app.mission import store as ms
            if plan.mission_id:
                m = ms.get(plan.mission_id)
                if m is not None and plan.task_id in m.task_ids:
                    return True, ""
                # mission missing or task not attached
                if m is None:
                    return False, f"mission {plan.mission_id} not found for task check"
                return False, f"task {plan.task_id} not attached to mission {plan.mission_id}"
            # no mission to verify against — task_id presence is sufficient
            return True, ""
        except Exception as e:   # pragma: no cover - defensive
            return False, f"task lookup failed: {e}"

    @staticmethod
    def _check_parameters(plan: ExecutionPlan) -> tuple[bool, str]:
        for step in plan.steps:
            if not step.target_description or not step.target_description.strip():
                return False, f"step {step.order} missing target_description"
            if step.action_type == ActionType.navigate:
                url = step.parameters.get("url")
                if not url:
                    return False, f"step {step.order} (NAVIGATE) missing 'url' parameter"
        return True, ""

    @staticmethod
    def _check_rollback(plan: ExecutionPlan) -> tuple[bool, str]:
        for step in plan.steps:
            if step.requires_rollback and not step.has_rollback:
                return False, f"step {step.order} ({step.action_type.value}) is mutating but has no rollback action"
        return True, ""


# ── Module-level singleton ────────────────────────────────────────────────────

_validator = PlanValidator()


def validate(plan: ExecutionPlan) -> PlanValidationResult:
    return _validator.validate(plan)
