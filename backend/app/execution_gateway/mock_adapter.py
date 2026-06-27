"""
Phase B — Execution Gateway V1 — MockBrowserAdapter.

A fully DETERMINISTIC mock adapter. Every operation returns a successful
AdapterResult with a fixed simulated duration, a log line, and a validation flag.

NO Playwright. NO Selenium. NO CDP. NO DOM. NO network. NO sleeps.

The reported `duration_ms` is SIMULATED metadata (not wall-clock); the adapter
itself runs in microseconds. Failure and validation-failure are driven
deterministically via constructor sets so tests can exercise every path without
randomness.
"""
from __future__ import annotations

from typing import Optional

from app.execution_gateway.adapter import ExecutionAdapter
from app.execution_gateway.models import AdapterResult, CommandType, ExecutionCommand

# Simulated per-command durations (ms) — deterministic, not wall-clock.
SIMULATED_DURATION_MS: dict[CommandType, float] = {
    CommandType.navigate: 5.0,
    CommandType.click:    2.0,
    CommandType.type:     3.0,
    CommandType.wait:     10.0,
    CommandType.extract:  4.0,
    CommandType.validate: 1.0,
    CommandType.upload:   8.0,
    CommandType.download: 8.0,
    CommandType.custom:   2.0,
}


class MockBrowserAdapter(ExecutionAdapter):
    """
    Deterministic mock. By default every operation succeeds and validates.

    To exercise failure paths deterministically:
      failure_steps          : step_ids whose dispatch returns success=False
      validation_fail_steps  : step_ids whose dispatch returns validation_passed=False
      flaky_steps            : step_ids that fail once per (step_id) then succeed
                               (used to exercise the retry engine deterministically)
    """

    name = "mock"

    def __init__(
        self,
        *,
        failure_steps:         Optional[set[str]] = None,
        validation_fail_steps: Optional[set[str]] = None,
        flaky_steps:           Optional[set[str]] = None,
    ) -> None:
        self.failure_steps         = set(failure_steps or set())
        self.validation_fail_steps = set(validation_fail_steps or set())
        self.flaky_steps           = set(flaky_steps or set())
        self._attempt_counts: dict[str, int] = {}
        self.dispatched: list[str] = []   # command_ids dispatched, in order

    # ── operations (all identical mock shape, distinct command_type) ───────────

    def navigate(self, command: ExecutionCommand) -> AdapterResult:       return self._run(command, CommandType.navigate)
    def click(self, command: ExecutionCommand) -> AdapterResult:          return self._run(command, CommandType.click)
    def type(self, command: ExecutionCommand) -> AdapterResult:           return self._run(command, CommandType.type)
    def wait(self, command: ExecutionCommand) -> AdapterResult:           return self._run(command, CommandType.wait)
    def extract(self, command: ExecutionCommand) -> AdapterResult:        return self._run(command, CommandType.extract)
    def validate(self, command: ExecutionCommand) -> AdapterResult:       return self._run(command, CommandType.validate)
    def upload(self, command: ExecutionCommand) -> AdapterResult:         return self._run(command, CommandType.upload)
    def download(self, command: ExecutionCommand) -> AdapterResult:       return self._run(command, CommandType.download)
    def execute_custom(self, command: ExecutionCommand) -> AdapterResult: return self._run(command, CommandType.custom)

    # ── deterministic core ─────────────────────────────────────────────────────

    def _run(self, command: ExecutionCommand, ctype: CommandType) -> AdapterResult:
        self.dispatched.append(command.command_id)
        duration = SIMULATED_DURATION_MS.get(ctype, 2.0)
        sid = command.step_id

        # Flaky: fail the FIRST attempt for this step, then succeed.
        if sid in self.flaky_steps:
            seen = self._attempt_counts.get(sid, 0)
            self._attempt_counts[sid] = seen + 1
            if seen == 0:
                return AdapterResult(
                    success=False, duration_ms=duration,
                    logs=[f"[mock] {ctype.value} flaky first-attempt failure for {sid}"],
                    output={"target": command.target_description},
                    validation_passed=False,
                    message="flaky transient failure",
                )

        if sid in self.failure_steps:
            return AdapterResult(
                success=False, duration_ms=duration,
                logs=[f"[mock] {ctype.value} simulated dispatch failure for {sid}"],
                output={"target": command.target_description},
                validation_passed=False,
                message="simulated dispatch failure",
            )

        validation_passed = sid not in self.validation_fail_steps
        return AdapterResult(
            success=True, duration_ms=duration,
            logs=[f"[mock] {ctype.value} ok -> {command.target_description}"],
            output={
                "target":     command.target_description,
                "parameters": command.parameters,
                "simulated":  True,
            },
            validation_passed=validation_passed,
            message="ok" if validation_passed else "validation mismatch",
        )

    def reset(self) -> None:
        self._attempt_counts.clear()
        self.dispatched.clear()
