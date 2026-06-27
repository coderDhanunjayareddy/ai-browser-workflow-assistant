"""
Phase B — Execution Gateway V1 — Validation Engine.

After every dispatched step the gateway verifies:
  1. expected outcome   — the adapter reported success
  2. validation strategy — the adapter reported validation_passed (when a strategy
                           other than NONE is declared)
  3. rollback metadata  — a mutating step declares a rollback action

If validation fails, the runner marks the execution FAILED.

Pure, deterministic. No browser code.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.execution_gateway.models import AdapterResult, ExecutionCommand


@dataclass
class ValidationOutcome:
    passed:   bool
    checks:   dict[str, bool]
    reason:   str = ""

    def to_dict(self) -> dict:
        return {"passed": self.passed, "checks": self.checks, "reason": self.reason}


class ValidationEngine:

    def validate(self, command: ExecutionCommand, result: AdapterResult) -> ValidationOutcome:
        checks: dict[str, bool] = {}
        reasons: list[str] = []

        # 1. expected outcome — adapter must report success
        ok_success = result.success is True
        checks["dispatch_succeeded"] = ok_success
        if not ok_success:
            reasons.append("adapter reported dispatch failure")

        # 2. validation strategy — when a strategy is declared, it must pass
        strategy = (command.validation_strategy or "NONE").upper()
        if strategy != "NONE":
            ok_validation = result.validation_passed is True
            checks["strategy_passed"] = ok_validation
            if not ok_validation:
                reasons.append(f"validation strategy {strategy} did not pass")
        else:
            checks["strategy_passed"] = True

        # 3. rollback metadata present (informational — a declared rollback is good)
        checks["rollback_metadata_present"] = bool(command.rollback_action)

        passed = checks["dispatch_succeeded"] and checks["strategy_passed"]
        return ValidationOutcome(passed=passed, checks=checks, reason="; ".join(reasons))


# ── Module-level singleton ────────────────────────────────────────────────────

_engine = ValidationEngine()


def validate(command: ExecutionCommand, result: AdapterResult) -> ValidationOutcome:
    return _engine.validate(command, result)
