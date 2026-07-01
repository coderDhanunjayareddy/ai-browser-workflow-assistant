"""
M0 — Criterion evaluation.

Evaluates success + failure criteria against the loop's observable state. Pure and
testable: DOM-element presence is supplied as a callback (`element_present`) so this
module never touches a browser directly. The same evaluator is used after every step
(for completion detection) and once at the end (for the final verdict).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from benchmark.m0_models import (
    M0Criterion, M0CriterionKind, M0FailureCriterion, FailureCriterionKind, CriterionResult,
)


@dataclass
class EvalContext:
    """Everything a criterion can be evaluated against."""
    final_url:      str = ""
    page_text:      str = ""                 # visible_text of the latest observation
    analysis_texts: list[str] = field(default_factory=list)  # every AI `analysis` string seen
    steps_taken:    int = 0
    http_errors:    list[str] = field(default_factory=list)  # observed status codes as strings
    rate_limited:   bool = False
    # selector -> bool. Defaults to "not present" when no probe is wired (offline tests).
    element_present: Callable[[str], bool] = lambda _sel: False

    @property
    def all_analysis(self) -> str:
        return "\n".join(self.analysis_texts)


def _eval_one(c: M0Criterion, ctx: EvalContext) -> CriterionResult:
    k = c.kind
    target = c.target or ""
    try:
        if k == M0CriterionKind.url_matches:
            ok = bool(re.search(target, ctx.final_url or "", re.IGNORECASE))
            return CriterionResult(k.value, c.detail, ok, f"url={ctx.final_url!r}")

        if k == M0CriterionKind.dom_element_present:
            ok = bool(ctx.element_present(target))
            return CriterionResult(k.value, c.detail, ok, f"selector={target!r} present={ok}")

        if k == M0CriterionKind.dom_text_present:
            ok = target.lower() in (ctx.page_text or "").lower()
            return CriterionResult(k.value, c.detail, ok, f"text~={target!r} found={ok}")

        if k == M0CriterionKind.dom_text_absent:
            ok = target.lower() not in (ctx.page_text or "").lower()
            return CriterionResult(k.value, c.detail, ok, f"text~={target!r} absent={ok}")

        if k == M0CriterionKind.extracted_value_present:
            ok = target.lower() in ctx.all_analysis.lower()
            return CriterionResult(k.value, c.detail, ok, f"key~={target!r} in analysis={ok}")

        if k == M0CriterionKind.extracted_value_matches:
            ok = bool(re.search(target, ctx.all_analysis, re.IGNORECASE))
            return CriterionResult(k.value, c.detail, ok, f"regex={target!r} matched={ok}")

        if k == M0CriterionKind.step_count_in_range:
            bound = c.value if c.value is not None else 1_000_000
            ok = ctx.steps_taken <= bound
            return CriterionResult(k.value, c.detail, ok, f"steps={ctx.steps_taken} <= {bound}")

        if k == M0CriterionKind.min_completed_steps:
            need = c.value or 1
            ok = ctx.steps_taken >= need
            return CriterionResult(k.value, c.detail, ok, f"steps={ctx.steps_taken} >= {need}")
    except re.error as e:
        return CriterionResult(k.value, c.detail, False, f"bad-regex: {e}")
    return CriterionResult(k.value, c.detail, False, "unknown criterion")


def evaluate_success(criteria: list[M0Criterion], ctx: EvalContext) -> list[CriterionResult]:
    return [_eval_one(c, ctx) for c in criteria]


def all_passed(results: list[CriterionResult]) -> bool:
    return bool(results) and all(r.passed for r in results)


def evaluate_failure(criteria: list[M0FailureCriterion], ctx: EvalContext) -> CriterionResult | None:
    """Return the first TRIPPED failure criterion, or None if none tripped."""
    for c in criteria:
        k = c.kind
        target = c.target or ""
        tripped = False
        observed = ""
        if k == FailureCriterionKind.dom_error_present:
            tripped = target.lower() in (ctx.page_text or "").lower()
            observed = f"error-text~={target!r} present={tripped}"
        elif k == FailureCriterionKind.url_matches_error:
            try:
                tripped = bool(re.search(target, ctx.final_url or "", re.IGNORECASE))
            except re.error:
                tripped = False
            observed = f"url={ctx.final_url!r}"
        elif k == FailureCriterionKind.http_error:
            tripped = target in ctx.http_errors
            observed = f"http_errors={ctx.http_errors}"
        elif k == FailureCriterionKind.rate_limited:
            tripped = ctx.rate_limited
            observed = f"rate_limited={ctx.rate_limited}"
        if tripped:
            return CriterionResult(k.value, c.detail, False, observed)
    return None
