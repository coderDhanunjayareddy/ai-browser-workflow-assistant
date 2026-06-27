"""
Phase B — Execution Gateway V1 — ExecutionRunner.

Drives an ExecutionPlan's steps through the dispatcher and adapter, updating the
ExecutionRecord after every step. Handles deterministic retry, per-step validation,
audit recording, and rollback simulation on terminal failure.

  ExecutionPlan -> steps -> Dispatcher -> Adapter -> Result -> Validation -> State

NO browser code. The adapter (a mock in V1) performs the simulated work.
"""
from __future__ import annotations

import time

from app.execution_gateway import audit as audit_trail
from app.execution_gateway import dispatcher as dispatcher_module
from app.execution_gateway import retry_engine
from app.execution_gateway import rollback_engine
from app.execution_gateway import validation as validation_engine
from app.execution_gateway.adapter import ExecutionAdapter
from app.execution_gateway.models import (
    ExecutionRecord,
    ExecutionState,
    StepExecution,
    StepOutcome,
    make_audit_entry,
)
from app.execution_planning.models import ExecutionPlan


class ExecutionRunner:

    def run(
        self,
        record:  ExecutionRecord,
        plan:    ExecutionPlan,
        adapter: ExecutionAdapter,
    ) -> ExecutionRecord:
        """
        Run remaining steps (from record.current_step_index) to completion or first
        terminal failure. Idempotent w.r.t. already-completed steps — supports resume.
        """
        record.state = ExecutionState.running
        if record.started_at is None:
            record.started_at = time.time()
        record.updated_at = time.time()

        steps = sorted(plan.steps, key=lambda s: s.order)

        while record.current_step_index < len(steps):
            step = steps[record.current_step_index]
            step_exec = self._run_step(record, step, adapter)
            record.step_executions.append(step_exec)
            record.current_step_index += 1

            if step_exec.outcome == StepOutcome.success:
                record.completed_steps += 1
            else:
                record.failed_steps += 1
                # Terminal failure → mark FAILED, simulate rollback of completed steps.
                record.state = ExecutionState.failed
                completed = [s for s in record.step_executions if s.outcome == StepOutcome.success]
                report = rollback_engine.simulate(completed)
                record.rollback_history = report
                if report:
                    audit_trail.append(make_audit_entry(
                        execution_id      = record.execution_id,
                        step_id           = step.step_id,
                        order             = step.order,
                        command_type      = step_exec.command_type,
                        timestamp         = time.time(),
                        duration_ms       = 0.0,
                        outcome           = "ROLLBACK_SIMULATED",
                        validation_passed = False,
                        retry_count       = max(0, step_exec.attempts - 1),
                        rollback_performed= True,
                        message           = f"rolled back {len(report)} completed step(s)",
                    ))
                record.finished_at = time.time()
                record.updated_at  = record.finished_at
                return record

        # All steps succeeded.
        record.state = ExecutionState.completed
        record.finished_at = time.time()
        record.updated_at  = record.finished_at
        return record

    # ── single step with retry + validation + audit ───────────────────────────

    def _run_step(self, record: ExecutionRecord, step, adapter: ExecutionAdapter) -> StepExecution:
        command = dispatcher_module.to_command(step)
        cfg = record.retry_config

        started_at = time.time()
        attempts = 0
        total_duration = 0.0
        last_result = None
        last_validation = None

        while True:
            attempts += 1
            result = dispatcher_module.dispatch(command, adapter)
            total_duration += result.duration_ms
            validation = validation_engine.validate(command, result)
            last_result, last_validation = result, validation

            # Audit every dispatched attempt.
            audit_trail.append(make_audit_entry(
                execution_id      = record.execution_id,
                step_id           = step.step_id,
                order             = step.order,
                command_type      = command.command_type.value,
                timestamp         = time.time(),
                duration_ms       = result.duration_ms,
                outcome           = "SUCCESS" if (result.success and validation.passed) else "FAILED",
                validation_passed = validation.passed,
                retry_count       = attempts - 1,
                rollback_performed= False,
                message           = result.message,
            ))

            if result.success and validation.passed:
                break

            dispatch_failed   = not result.success
            validation_failed = not validation.passed
            if not retry_engine.should_retry(attempts, cfg,
                                             dispatch_failed=dispatch_failed,
                                             validation_failed=validation_failed):
                break

        # Determine outcome
        if last_result.success and last_validation.passed:
            outcome = StepOutcome.success
        elif not last_result.success:
            outcome = StepOutcome.failed
        else:
            outcome = StepOutcome.validation_failed

        return StepExecution(
            step_id           = step.step_id,
            order             = step.order,
            action_type       = step.action_type.value,
            command_type      = command.command_type.value,
            outcome           = outcome,
            attempts          = attempts,
            duration_ms       = round(total_duration, 3),
            validation_passed = last_validation.passed,
            output            = last_result.output,
            logs              = last_result.logs,
            message           = last_result.message,
            started_at        = started_at,
            finished_at       = time.time(),
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_runner = ExecutionRunner()


def run(record: ExecutionRecord, plan: ExecutionPlan, adapter: ExecutionAdapter) -> ExecutionRecord:
    return _runner.run(record, plan, adapter)
