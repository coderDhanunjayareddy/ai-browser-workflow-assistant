"""Production Planner Recovery (PR-1).

Planner Recovery is a one-turn planner-context signal. It never plans, executes,
recovers, retries, validates, or changes planner output. It only marks the next
planner invocation as recovery mode after Goal Convergence and Strategy
Generation have already produced recovery context.
"""
from __future__ import annotations

from app.schemas.request import PageContext, PriorStep


_PENDING_RECOVERY: set[str] = set()


def reset_planner_recovery(session_id: str) -> None:
    """Clear pending Planner Recovery state for a session."""
    _PENDING_RECOVERY.discard(session_id)


def prepare_planner_recovery_if_strategy_context(
    *,
    session_id: str,
    goal_convergence: bool,
    strategy_context_prepared: bool,
) -> bool:
    """Arm exactly one recovery planner turn when GC and SG both fired."""
    if not goal_convergence or not strategy_context_prepared:
        return False

    _PENDING_RECOVERY.add(session_id)
    return True


def consume_recovery_prior_steps(
    *,
    session_id: str,
    prior_steps: list[PriorStep],
    page_context: PageContext,
) -> list[PriorStep]:
    """Append the one-shot recovery marker to the next planner request."""
    if session_id not in _PENDING_RECOVERY:
        return prior_steps

    _PENDING_RECOVERY.discard(session_id)
    return [
        *prior_steps,
        PriorStep(
            action_type="replan",
            description="Planner Recovery: one-turn recovery planning",
            target_selector="",
            value=None,
            execution_result=(
                "RECOVERY MODE: Goal Convergence marked the previous strategy "
                "as stalled; use the existing Strategy Generation context for "
                "this planner turn"
            ),
            page_analysis=(
                "PLANNER RECOVERY MODE\n"
                "This is a one-turn recovery planning cycle after Goal "
                "Convergence detected semantic non-progress.\n"
                "Use the Strategy Generation context already present in "
                "prior_steps. Choose one valid Planner Contract V2 outcome "
                "that does not simply continue the failed strategy unless new "
                "evidence supports it."
            ),
            page_url=page_context.url,
            page_title=page_context.title,
        ),
    ]


def has_pending_planner_recovery(session_id: str) -> bool:
    return session_id in _PENDING_RECOVERY
