"""Production Strategy Generation (SG-1).

This module is context-only. It never plans, recovers, executes, or changes a
planner response. It reuses the benchmark Strategy Generation formatter and
stores one pending context for the next planner invocation after Goal
Convergence reports semantic stagnation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from benchmark.strategy_generation import StrategyContext, build_strategy_context

from app.schemas.request import PageContext, PriorStep
from app.schemas.response import AnalyzeResponse


@dataclass(frozen=True)
class _ValidationMiss:
    kind: str
    detail: str
    observed: str
    passed: bool = False


_PENDING_CONTEXTS: dict[str, StrategyContext] = {}
_EMITTED_CONTEXT_KEYS: dict[str, set[str]] = {}


def reset_strategy_generation(session_id: str) -> None:
    """Clear pending and emitted Strategy Generation state for a session."""
    _PENDING_CONTEXTS.pop(session_id, None)
    _EMITTED_CONTEXT_KEYS.pop(session_id, None)


def prepare_strategy_context_if_stalled(
    *,
    session_id: str,
    goal_convergence: bool,
    task: str,
    page_context: PageContext,
    planner_response: AnalyzeResponse,
    convergence_reason: str = "semantic evidence unchanged across planner turns",
) -> bool:
    """Prepare context for the next planner turn only when convergence fired."""
    if not goal_convergence:
        return False

    strategy_context = build_strategy_context(
        goal=task,
        success_criteria=[],
        validation_results=_validation_misses(planner_response, page_context),
        page_context=page_context.model_dump(),
        outcome_kind=planner_response.outcome_kind,
        strategy_key=_strategy_key(planner_response),
        convergence_reason=convergence_reason,
    )

    emitted = _EMITTED_CONTEXT_KEYS.setdefault(session_id, set())
    if strategy_context.context_key in emitted:
        return False

    emitted.add(strategy_context.context_key)
    _PENDING_CONTEXTS[session_id] = strategy_context
    return True


def consume_strategy_prior_steps(
    *,
    session_id: str,
    prior_steps: list[PriorStep],
    page_context: PageContext,
) -> list[PriorStep]:
    """Append pending Strategy Generation context to this planner request."""
    strategy_context = _PENDING_CONTEXTS.pop(session_id, None)
    if strategy_context is None:
        return prior_steps

    return [
        *prior_steps,
        PriorStep(
            action_type="replan",
            description="Strategy Generation: previous strategy stalled",
            target_selector="",
            value=None,
            execution_result=(
                "FAILED: current strategy is not making semantic progress; "
                "use strategy context before choosing the next outcome"
            ),
            page_analysis=strategy_context.text,
            page_url=page_context.url,
            page_title=page_context.title,
        ),
    ]


def has_pending_strategy_context(session_id: str) -> bool:
    return session_id in _PENDING_CONTEXTS


def _strategy_key(planner_response: AnalyzeResponse) -> str:
    if planner_response.outcome_kind == "report":
        return "report"

    if planner_response.suggested_actions:
        action = planner_response.suggested_actions[0]
        value = "" if action.value is None else str(action.value)
        return f"{action.action_type}|{action.target_selector}|{value}"

    return planner_response.outcome_kind


def _validation_misses(
    planner_response: AnalyzeResponse,
    page_context: PageContext,
) -> list[Any]:
    if planner_response.outcome_kind != "report" or planner_response.sgv_verified:
        return []

    answer = planner_response.report.answer if planner_response.report else None
    observed = _observed_summary(page_context)
    return [
        _ValidationMiss(
            kind="semantic_goal_validation",
            detail=f"report answer {answer!r} not verified",
            observed=observed,
        )
    ]


def _observed_summary(page_context: PageContext) -> str:
    text = " ".join((page_context.visible_text or "").split())
    if len(text) > 140:
        text = text[:137] + "..."
    return text or f"url={page_context.url!r}; title={page_context.title!r}"
