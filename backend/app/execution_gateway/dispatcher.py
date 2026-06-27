"""
Phase B — Execution Gateway V1 — ExecutionDispatcher.

Maps a V9.0 ExecutionStep to an abstract ExecutionCommand and dispatches it to an
adapter. DISPATCH ONLY — there is no browser code here. The dispatcher never decides
success/failure; the adapter returns an AdapterResult.
"""
from __future__ import annotations

from app.execution_gateway.adapter import ExecutionAdapter
from app.execution_gateway.models import (
    AdapterResult,
    CommandType,
    ExecutionCommand,
    make_command,
)
from app.execution_planning.models import ActionType, ExecutionStep

# V9.0 ActionType → gateway CommandType. Permanent mapping.
ACTION_TO_COMMAND: dict[ActionType, CommandType] = {
    ActionType.navigate: CommandType.navigate,
    ActionType.read:     CommandType.extract,
    ActionType.extract:  CommandType.extract,
    ActionType.input:    CommandType.type,
    ActionType.click:    CommandType.click,
    ActionType.scroll:   CommandType.custom,
    ActionType.wait:     CommandType.wait,
    ActionType.validate: CommandType.validate,
}


class ExecutionDispatcher:

    def to_command(self, step: ExecutionStep) -> ExecutionCommand:
        ctype = ACTION_TO_COMMAND.get(step.action_type, CommandType.custom)
        return make_command(
            ctype,
            step.step_id,
            step.order,
            step.target_description,
            parameters          = dict(step.parameters),
            expected_result     = step.expected_result,
            validation_strategy = step.validation_strategy.value,
            rollback_action     = step.rollback_action.value,
        )

    def dispatch(self, command: ExecutionCommand, adapter: ExecutionAdapter) -> AdapterResult:
        """Route the command through the adapter. No browser code; pure delegation."""
        return adapter.dispatch(command)


# ── Module-level singleton ────────────────────────────────────────────────────

_dispatcher = ExecutionDispatcher()


def to_command(step: ExecutionStep) -> ExecutionCommand:
    return _dispatcher.to_command(step)

def dispatch(command: ExecutionCommand, adapter: ExecutionAdapter) -> AdapterResult:
    return _dispatcher.dispatch(command, adapter)
