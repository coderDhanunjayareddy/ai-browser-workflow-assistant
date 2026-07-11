"""Strategy Generation context for convergence-triggered replans.

This module does not plan. It only formats existing loop evidence so the next
planner invocation can see why the previous strategy stopped converging.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class StrategyContext:
    context_key: str
    text: str


def build_strategy_context(
    *,
    goal: str,
    success_criteria: list[Any],
    validation_results: list[Any],
    page_context: dict,
    outcome_kind: str,
    strategy_key: str,
    convergence_reason: str,
) -> StrategyContext:
    missing = [r for r in validation_results if not getattr(r, "passed", False)]
    expected = _expected_goal(goal, success_criteria)
    observed = _observed_evidence(page_context)
    contradiction = _contradiction(expected=expected, missing=missing, page_context=page_context)
    failed_strategy = _failed_strategy(outcome_kind, strategy_key)
    avoid = _avoid_class(outcome_kind, strategy_key, missing)
    validation_summary = _validation_summary(missing)

    key = "|".join([
        outcome_kind,
        strategy_key,
        validation_summary,
        page_context.get("url", ""),
    ])

    text = "\n".join([
        "STRATEGY GENERATION CONTEXT",
        f"Expected semantic goal: {expected}",
        f"Observed evidence: {observed}",
        f"Contradiction detected: {contradiction}",
        f"Repeatedly failed strategy: {failed_strategy}",
        f"Avoid next: {avoid}",
        f"Validation still missing: {validation_summary}",
        f"Goal convergence reason: {convergence_reason}",
        (
            "Planner freedom: choose any valid Planner Contract V2 outcome, but do not "
            "continue the avoided strategy unless new evidence changes the situation."
        ),
    ])
    return StrategyContext(context_key=key, text=text)


def _expected_goal(goal: str, success_criteria: list[Any]) -> str:
    parts = [goal.strip()] if goal else []
    for criterion in success_criteria:
        kind = getattr(getattr(criterion, "kind", None), "value", getattr(criterion, "kind", ""))
        target = getattr(criterion, "target", None)
        detail = getattr(criterion, "detail", "")
        label = detail or kind
        if target:
            parts.append(f"{label}: {target}")
        elif label:
            parts.append(str(label))
    return "; ".join(p for p in parts if p) or "current user goal"


def _observed_evidence(page_context: dict) -> str:
    text = " ".join(str(page_context.get("visible_text", "")).split())
    if len(text) > 180:
        text = text[:177] + "..."
    bits = [
        f"url={page_context.get('url', '')!r}",
        f"title={page_context.get('title', '')!r}",
    ]
    if text:
        bits.append(f"text={text!r}")
    return "; ".join(bits)


def _contradiction(*, expected: str, missing: list[Any], page_context: dict) -> str:
    if not missing:
        return "goal evidence changed before completion; do not assume completion without validation"
    observed = "; ".join(getattr(r, "observed", "") for r in missing if getattr(r, "observed", ""))
    if not observed:
        observed = f"url={page_context.get('url', '')!r}; title={page_context.get('title', '')!r}"
    return f"expected {expected}; observed {observed}"


def _failed_strategy(outcome_kind: str, strategy_key: str) -> str:
    if outcome_kind == "report":
        return "repeated unsupported report from unchanged semantic evidence"
    if strategy_key:
        return f"repeated {outcome_kind} strategy {strategy_key!r}"
    return f"repeated {outcome_kind} strategy"


def _avoid_class(outcome_kind: str, strategy_key: str, missing: list[Any]) -> str:
    if outcome_kind == "report":
        return "unsupported reports or completion claims until validation evidence changes"
    if missing:
        missing_kinds = ", ".join(str(getattr(r, "kind", "")) for r in missing if getattr(r, "kind", ""))
        if missing_kinds:
            return f"same {outcome_kind} route that leaves {missing_kinds} unsatisfied"
    action_type = strategy_key.split("|", 1)[0] if strategy_key else outcome_kind
    return f"same repeated {action_type} action/target without semantic progress"


def _validation_summary(missing: list[Any]) -> str:
    if not missing:
        return "none"
    parts = []
    for result in missing:
        kind = getattr(result, "kind", "")
        detail = getattr(result, "detail", "")
        observed = getattr(result, "observed", "")
        label = detail or kind or "criterion"
        parts.append(f"{label} ({observed})" if observed else str(label))
    return "; ".join(parts)
