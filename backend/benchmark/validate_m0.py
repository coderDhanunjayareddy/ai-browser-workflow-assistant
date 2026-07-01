"""
M0 — Validation suite (standalone, offline).

Exercises every benchmark component end-to-end with test doubles and prints a PASS/FAIL
checklist + a final count. No browser, no network, no AI. Mirrors the repo's validate_v*.py
convention. Exit code 0 iff every check passes.

Usage:  python -m benchmark.validate_m0
"""
from __future__ import annotations

import json
import sys

from benchmark import m0_scenarios, m0_metrics, m0_report, criteria, failure_classifier
from benchmark.m0_models import (
    M0Criterion, M0CriterionKind, M0FailureCriterion, FailureCriterionKind,
    M0TaskDefinition, Difficulty, BenchmarkCategory, Preconditions, HumanInterventionRules,
    TaskStatus, FailureCategory,
)
from benchmark.failure_classifier import FailureSignal
from benchmark.m0_task_runner import TaskRunner
from benchmark.fakes import FakeDriver, FakeAnalyzeClient, page
from benchmark.m0_executor import ExecResult


_checks: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    _checks.append((name, bool(cond), detail))


def _runner(driver, client, mode="playwright"):
    import tempfile
    return TaskRunner(driver=driver, client=client, executor_mode=mode,
                      run_id="validate", artifacts_dir=tempfile.gettempdir())


def _simple_task(**kw) -> M0TaskDefinition:
    defaults = dict(
        task_id="t_demo", site_id="fixture_server", website="Demo", difficulty=Difficulty.simple,
        category=BenchmarkCategory.search, goal="demo", start_url="http://x/login",
        max_steps=6, retry_budget=1)
    defaults.update(kw)
    return M0TaskDefinition(**defaults)


def run() -> int:
    # ── 1. scenarios well-formed ────────────────────────────────────────────
    tasks = m0_scenarios.build_m0_scenarios()
    check("27 scenarios defined", len(tasks) == 27, f"got {len(tasks)}")
    ids = [t.task_id for t in tasks]
    check("scenario ids unique", len(ids) == len(set(ids)))
    check("every scenario has success criteria", all(t.success_criteria for t in tasks))
    check("every scenario serializes", all(isinstance(t.to_dict(), dict) for t in tasks))
    check("fixture tasks use {fixture_base}",
          all("{fixture_base}" in t.start_url for t in tasks if t.is_fixture))
    check("expect_failure tasks present (cross-site + sheets)",
          sum(1 for t in tasks if t.expect_failure) >= 2)

    # ── 2. criteria evaluators ──────────────────────────────────────────────
    ctx = criteria.EvalContext(final_url="https://x/r?search_query=Python",
                               page_text="Python tutorial results", analysis_texts=["price is ₹999"],
                               steps_taken=3, element_present=lambda s: s == "#ok")
    res = criteria.evaluate_success([
        M0Criterion(M0CriterionKind.url_matches, target=r"search_query=Python"),
        M0Criterion(M0CriterionKind.dom_text_present, target="Python tutorial"),
        M0Criterion(M0CriterionKind.dom_text_absent, target="error"),
        M0Criterion(M0CriterionKind.extracted_value_present, target="₹"),
        M0Criterion(M0CriterionKind.min_completed_steps, value=2),
        M0Criterion(M0CriterionKind.dom_element_present, target="#ok"),
    ], ctx)
    check("all six success criteria pass", criteria.all_passed(res),
          str([(r.kind, r.passed) for r in res]))
    neg = criteria.evaluate_success([M0Criterion(M0CriterionKind.dom_text_present, target="absent-xyz")], ctx)
    check("missing text fails", not criteria.all_passed(neg))

    # ── 3. failure criteria ─────────────────────────────────────────────────
    fctx = criteria.EvalContext(final_url="https://x/login", page_text="please log in",
                                http_errors=["429"])
    trip = criteria.evaluate_failure([
        M0FailureCriterion(FailureCriterionKind.http_error, target="429")], fctx)
    check("http 429 failure criterion trips", trip is not None)
    notrip = criteria.evaluate_failure([
        M0FailureCriterion(FailureCriterionKind.dom_error_present, target="catastrophe")], fctx)
    check("absent error does not trip", notrip is None)

    # ── 4. failure classifier decision tree ─────────────────────────────────
    cls = failure_classifier.classify
    check("captcha -> BLOCKED_CAPTCHA",
          cls(FailureSignal(page_text="Please complete the CAPTCHA")) == FailureCategory.blocked_captcha)
    check("429 -> BLOCKED_RATE_LIMIT",
          cls(FailureSignal(http_status=429)) == FailureCategory.blocked_rate_limit)
    check("login wall -> BLOCKED_LOGIN_WALL",
          cls(FailureSignal(page_text="Log in to continue")) == FailureCategory.blocked_login_wall)
    check("auth url -> BLOCKED_AUTH_EXPIRED",
          cls(FailureSignal(final_url="https://accounts.google.com/signin")) == FailureCategory.blocked_auth_expired)
    check("locator all failed -> GROUNDING",
          cls(FailureSignal(locator_all_failed=True)) == FailureCategory.grounding)
    check("visible-not-in-dom -> PERCEPTION",
          cls(FailureSignal(locator_all_failed=True, element_visible_pixels=True,
                            element_in_dom=False)) == FailureCategory.perception)
    check("executed no-change -> EXECUTION",
          cls(FailureSignal(executed=True, dom_changed=False)) == FailureCategory.execution)
    check("needs_visual -> VISION_REQUIRED",
          cls(FailureSignal(needs_visual=True)) == FailureCategory.vision_required)
    check("infra error -> INFRASTRUCTURE",
          cls(FailureSignal(error_type="TimeoutError")) == FailureCategory.infrastructure)
    check("timed out -> TIMEOUT",
          cls(FailureSignal(timed_out=True)) == FailureCategory.timeout)
    check("cross-site -> ORCHESTRATION",
          cls(FailureSignal(is_cross_site=True)) == FailureCategory.orchestration)

    # ── 5. TaskRunner: completion ───────────────────────────────────────────
    driver = FakeDriver([
        page("http://x/login", text="login form", elements=[{"selector": "#u"}, {"selector": "#p"}]),
        page("http://x/login", text="Welcome tester now", elements=[]),
    ])
    client = FakeAnalyzeClient([("fill", "#u", "tester"), ("fill", "#p", "secret123"),
                               ("click", "#login-btn", None)])
    task = _simple_task(success_criteria=[
        M0Criterion(M0CriterionKind.dom_text_present, target="Welcome tester"),
        M0Criterion(M0CriterionKind.min_completed_steps, value=1)])
    out = _runner(driver, client).run(task)
    check("task completes when criteria met", out.status == TaskStatus.completed,
          f"status={out.status} steps={out.steps_taken}")
    check("completed task has criteria_results", bool(out.criteria_results))

    # ── 6. TaskRunner: grounding failure ────────────────────────────────────
    def fail_responder(action, idx):
        return ExecResult(False, "all locator strategies failed", locator_strategy=None,
                          locator_attempts=5)
    gd = FakeDriver([page("http://x/a", text="nothing useful", elements=[])],
                    responder=fail_responder)
    gc = FakeAnalyzeClient([("click", "button.missing", None)] * 4)
    gtask = _simple_task(success_criteria=[M0Criterion(M0CriterionKind.dom_text_present, target="done")],
                         retry_budget=1, max_steps=4)
    gout = _runner(gd, gc).run(gtask)
    check("grounding failure -> FAILED + GROUNDING", gout.status == TaskStatus.failed
          and gout.failure_category == FailureCategory.grounding.value,
          f"status={gout.status} cat={gout.failure_category}")

    # ── 7. TaskRunner: captcha block ────────────────────────────────────────
    cd = FakeDriver([page("http://x/a", text="x")], captcha=True)
    cout = _runner(cd, FakeAnalyzeClient([("click", "#x", None)])).run(_simple_task())
    check("captcha -> BLOCKED", cout.status == TaskStatus.blocked
          and cout.failure_category == FailureCategory.blocked_captcha.value)
    check("blocked task excluded from completion denominator", not cout.counts_toward_completion)

    # ── 8. metrics ──────────────────────────────────────────────────────────
    agg = m0_metrics.aggregate([out, gout, cout], executor_mode="playwright")
    # completed=1, counted = out + gout (cout blocked excluded) = 2 -> 0.5
    check("completion rate excludes blocked",
          agg["summary"]["completion_rate"] == 0.5, str(agg["summary"]["completion_rate"]))
    lo, hi = m0_metrics.wilson_interval(1, 2)
    check("wilson interval bounded", 0.0 <= lo <= 0.5 <= hi <= 1.0, f"[{lo},{hi}]")
    check("cost estimate positive", m0_metrics.estimate_cost_usd(1000, 200) > 0)
    check("failure distribution populated", agg["failure_distribution"].get("GROUNDING") == 1)

    # ── 9. reports render ───────────────────────────────────────────────────
    meta = {"run_id": "validate", "suite": "smoke", "executor_mode": "playwright", "duration_s": 1}
    report = m0_report.build_report(meta=meta, results=[out, gout, cout], executor_mode="playwright")
    check("JSON report serializes", isinstance(json.dumps(report), str))
    md = m0_report.render_markdown(report)
    check("markdown has completion header", "Task Completion Rate" in md)
    htmlr = m0_report.render_html(report)
    check("html self-contained (no external src)", "http-equiv" not in htmlr
          and "src=\"http" not in htmlr and "<style>" in htmlr and "window.__M0_REPORT__" in htmlr)

    # ── 10. baseline comparison ─────────────────────────────────────────────
    baseline = {"meta": {"run_id": "base"}, "summary": {"completion_rate": 0.80}}
    rep2 = m0_report.build_report(meta=meta, results=[out, gout, cout],
                                  executor_mode="playwright", baseline=baseline)
    delta = rep2["summary"].get("completion_rate_delta_from_baseline")
    check("baseline delta computed", delta is not None and abs(delta - (0.5 - 0.80)) < 1e-9,
          str(delta))

    # ── 11. executor gap ────────────────────────────────────────────────────
    gap = m0_metrics.executor_gap(agg, agg)
    check("executor gap zero for identical runs", gap["overall"]["gap"] == 0.0)

    # ── report ───────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok, _ in _checks if ok)
    total = len(_checks)
    print("\n=== M0 VALIDATION ===")
    for name, ok, detail in _checks:
        mark = "PASS" if ok else "FAIL"
        extra = f"  [{detail}]" if (detail and not ok) else ""
        print(f"  [{mark}] {name}{extra}")
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(run())
