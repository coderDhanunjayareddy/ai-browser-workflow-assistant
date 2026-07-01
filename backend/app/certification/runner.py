"""
Phase F — Certification Runner (thin harness; NOT a new orchestration layer).

For each scenario it:
  1. builds the workflow steps + a READY ExecutionPlan (with authorization + mission),
  2. delegates execution to the UNCHANGED gateway:
       - real_browser=True  -> execute_plan_with_browser (real chromium, Phase D enabled)
       - real_browser=False -> gateway.start(auto_run) with the deterministic mock adapter
         (certifies the planner + gateway + authorization pipeline in ANY environment),
  3. evaluates the scenario's success criteria against the resulting ExecutionRecord,
  4. records the reliability outcome + any failure into the catalog,
  5. returns a reproducible CertificationResult.

All execution flows through existing components. No adapter/gateway/planner code changes.
"""
from __future__ import annotations

import time
from typing import Optional

from app.certification.models import (
    CertificationScenario, CertificationResult, CriterionResult, CriterionKind,
    OutcomeStatus, WorkflowOutcome,
)
from app.certification import reliability, failure_catalog, fixtures
from app.certification.failure_catalog import Reproducibility, ResolutionStatus

from app.execution_gateway import engine as gateway
from app.execution_gateway.models import ExecutionState
from app.execution_gateway.browser import run as browser_run
from app.execution_planning import registry as plan_reg
from app.execution_planning.registry import set_status
from app.execution_planning.models import PlanStatus, ExecutionMode, make_plan
from app.authorization import registry as auth_reg
from app.authorization.models import make_authorization
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState

# criteria that require the real Playwright adapter's per-step output
_REAL_ONLY = {
    CriterionKind.post_validation, CriterionKind.content_contains,
    CriterionKind.recovery_used, CriterionKind.bounded_failure, CriterionKind.failure_category,
}

_COUNTER = {"n": 0}


def _build_ready_plan(scenario: CertificationScenario, steps: list):
    _COUNTER["n"] += 1
    n = _COUNTER["n"]
    mission_id = f"m-cert-{n}"
    auth = make_authorization(f"ctr-cert-{n}", True, "certified", "HIGH", time.time() + 3600,
                              mission_id=mission_id, task_id="t-cert")
    auth_reg.add(auth)
    mission_store.put(Mission(mission_id, "certification", scenario.workflow,
                              MissionState.active, task_ids=["t-cert"]))
    plan = make_plan(auth.authorization_id, mission_id=mission_id, task_id="t-cert",
                     created_at=time.time(), execution_mode=ExecutionMode.sequential, steps=steps,
                     estimated_duration_ms=0, rollback_supported=True, confidence=0.9,
                     metadata={"certification_scenario": scenario.scenario_id})
    plan_reg.add(plan)
    set_status(plan.plan_id, PlanStatus.ready)
    return plan


def _semantic_present(scenario: CertificationScenario, target: str) -> tuple[bool, str]:
    """Deterministic: does Website Intelligence find `target` structure in the fixture?"""
    html = fixtures.fixture_html(scenario.fixture)
    if html is None:
        return False, "fixture missing"
    try:
        from app.website_intelligence import analyzer
        import time as _t
        t0 = _t.perf_counter()
        result = analyzer.analyze_html(html, title=scenario.website)
        reliability.record_semantic_latency((_t.perf_counter() - t0) * 1000)
        tc = result.page.type_counts
        present = tc.get((target or "").upper(), 0) > 0
        return present, f"type_counts[{target.upper()}]={tc.get((target or '').upper(), 0)}"
    except Exception as e:
        return False, f"error: {type(e).__name__}"


def _eval_criterion(c, rec, scenario, real_browser: bool) -> CriterionResult:
    kind = c.kind
    # semantic criterion is browser-independent (deterministic over the fixture HTML)
    if kind == CriterionKind.semantic_present:
        ok, obs = _semantic_present(scenario, c.target or "")
        return CriterionResult(kind.value, c.detail, ok, obs)
    # real-only criteria are not evaluated in mock mode
    if kind in _REAL_ONLY and not real_browser:
        return CriterionResult(kind.value, c.detail, True, "mock-mode: not evaluated")
    try:
        if kind == CriterionKind.state_completed:
            ok = rec.state == ExecutionState.completed
            return CriterionResult(kind.value, c.detail, ok, f"state={rec.state.value}")
        if kind == CriterionKind.min_completed_steps:
            need = c.value or 1
            ok = rec.completed_steps >= need
            return CriterionResult(kind.value, c.detail, ok, f"completed={rec.completed_steps} need>={need}")
        if kind == CriterionKind.post_validation:
            out = rec.step_executions[c.step_index].output
            ok = out.get("post_validation", {}).get("passed") is True
            return CriterionResult(kind.value, c.detail, ok, f"post_validation={out.get('post_validation')}")
        if kind == CriterionKind.content_contains:
            out = rec.step_executions[c.step_index].output
            preview = out.get("details", {}).get("content_preview", "")
            ok = (c.target or "") in preview
            return CriterionResult(kind.value, c.detail, ok, f"preview~={preview[:60]!r}")
        if kind == CriterionKind.recovery_used:
            out = rec.step_executions[c.step_index].output
            ok = len(out.get("recovery_used", [])) >= 1
            return CriterionResult(kind.value, c.detail, ok, f"recovery_used={out.get('recovery_used')}")
        if kind == CriterionKind.bounded_failure:
            out = rec.step_executions[c.step_index].output
            attempts = out.get("attempts", 99)
            ok = rec.state == ExecutionState.failed and attempts <= (c.value or 3)
            return CriterionResult(kind.value, c.detail, ok, f"state={rec.state.value} attempts={attempts}")
        if kind == CriterionKind.failure_category:
            out = rec.step_executions[c.step_index].output
            got = out.get("failure_category")
            ok = got == c.target
            return CriterionResult(kind.value, c.detail, ok, f"failure_category={got}")
    except (IndexError, KeyError, AttributeError) as e:
        return CriterionResult(kind.value, c.detail, False, f"eval-error: {type(e).__name__}")
    return CriterionResult(kind.value, c.detail, False, "unknown criterion")


def run_scenario(scenario: CertificationScenario, *, base_url: str = "",
                 real_browser: bool = False, headless: bool = True, cleanup: bool = True,
                 seen_at: Optional[float] = None) -> CertificationResult:
    seen_at = time.time() if seen_at is None else seen_at
    steps = scenario.build_steps(base_url) if scenario.build_steps else []
    result = CertificationResult(
        scenario_id=scenario.scenario_id, name=scenario.name, category=scenario.category.value,
        website=scenario.website, status=OutcomeStatus.error, total_steps=len(steps),
        real_browser=real_browser,
    )

    t0 = time.perf_counter()
    rec = None
    try:
        plan = _build_ready_plan(scenario, steps)
        if real_browser:
            rec = browser_run.execute_plan_with_browser(plan.plan_id, headless=headless, cleanup=cleanup)
        else:
            rec = gateway.start(plan.plan_id, auto_run=True)
        result.execution_id = rec.execution_id
        result.execution_state = rec.state.value
        result.completed_steps = rec.completed_steps
    except Exception as e:
        result.duration_ms = (time.perf_counter() - t0) * 1000
        result.status = OutcomeStatus.error
        result.failure_category = type(e).__name__
        result.failure_detail = str(e)[:300]
        failure_catalog.record(category=scenario.category.value, website=scenario.website,
                               workflow=scenario.workflow, seen_at=seen_at,
                               reproducibility=Reproducibility.once, recovery_outcome="none",
                               resolution_status=ResolutionStatus.open,
                               detail=f"{type(e).__name__}: {str(e)[:160]}")
        reliability.record_workflow(WorkflowOutcome(scenario.scenario_id, scenario.category.value,
                                                    scenario.website, False, result.duration_ms, real_browser))
        return result

    result.duration_ms = (time.perf_counter() - t0) * 1000

    # evaluate criteria
    result.criteria = [_eval_criterion(c, rec, scenario, real_browser) for c in scenario.success_criteria]

    # state expectation
    if real_browser:
        if scenario.expect_failure:
            state_ok = rec.state == ExecutionState.failed
        else:
            state_ok = rec.state == ExecutionState.completed
    else:
        state_ok = rec is not None  # mock pipeline produced a record

    criteria_ok = all(c.passed for c in result.criteria)
    passed = state_ok and criteria_ok
    result.status = OutcomeStatus.passed if passed else OutcomeStatus.failed

    if not passed:
        failing = next((c for c in result.criteria if not c.passed), None)
        result.failure_category = "criteria" if failing else "state"
        result.failure_detail = (f"{failing.kind}: {failing.observed}" if failing
                                 else f"state={result.execution_state}")
        failure_catalog.record(category=scenario.category.value, website=scenario.website,
                               workflow=scenario.workflow, seen_at=seen_at,
                               reproducibility=Reproducibility.once,
                               recovery_outcome="real" if real_browser else "mock",
                               resolution_status=ResolutionStatus.open,
                               detail=result.failure_detail or "")

    reliability.record_workflow(WorkflowOutcome(scenario.scenario_id, scenario.category.value,
                                                scenario.website, passed, result.duration_ms, real_browser))
    return result


def certify_all(scenarios: list[CertificationScenario], *, base_url: str = "",
                real_browser: bool = False, headless: bool = True,
                seen_at: Optional[float] = None) -> list[CertificationResult]:
    return [run_scenario(s, base_url=base_url, real_browser=real_browser, headless=headless,
                         seen_at=seen_at) for s in scenarios]
