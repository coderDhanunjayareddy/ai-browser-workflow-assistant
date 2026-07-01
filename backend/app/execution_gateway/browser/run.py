"""
Phase C/D — Browser execution entrypoint.

Drives a real-browser execution through the EXISTING, UNCHANGED gateway API:

  1. gateway.start(plan_id, auto_run=False, retry_config=RetryConfig(max_retries=0))
       -> creates the ExecutionRecord (PENDING) and returns its execution_id
  2. build a PlaywrightAdapter bound to that execution_id
  3. gateway.resume(execution_id, adapter=playwright_adapter)
       -> runs the plan through Dispatcher -> PlaywrightAdapter -> Browser

RetryConfig(max_retries=0) makes the runner do exactly one dispatch per step; the
PlaywrightAdapter is the browser-retry authority (Phase C transient retries, Phase D
adaptive recovery). No gateway / runner / retry-engine code is modified.

Phase D (adaptive locator + deterministic recovery + first-class validation +
monitor/metrics/timeline) is enabled by default for REAL execution. The raw adapter
default remains Phase C-compatible, so all previous tests are unaffected.
"""
from __future__ import annotations

from typing import Optional

from app.execution_gateway import engine as gateway
from app.execution_gateway.models import ExecutionRecord, RetryConfig
from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
from app.execution_gateway.browser import exec_timeline as _exec_timeline


def execute_plan_with_browser(
    plan_id:         str,
    *,
    headless:        bool = True,
    cleanup:         bool = True,
    adaptive:        bool = True,
    recovery:        bool = True,
    post_validation: bool = True,
    retry_config:    Optional[RetryConfig] = None,
) -> ExecutionRecord:
    """Execute a READY plan against a real browser via Playwright (Phase D enabled)."""
    adapter = PlaywrightAdapter(
        headless=headless,
        adaptive=adaptive,
        recovery=recovery,
        post_validation=post_validation,
    )
    # Adapter handles its own (recovery-driven) retries; runner does exactly one dispatch.
    record = gateway.start(plan_id, auto_run=False, adapter=adapter,
                           retry_config=retry_config or RetryConfig(max_retries=0))
    adapter.execution_id = record.execution_id
    adapter.mission_id = record.mission_id

    # Phase D timeline: record the "planned" lifecycle event for each step up front.
    _record_planned(plan_id, record.execution_id)

    try:
        result = gateway.resume(record.execution_id, adapter=adapter)
        # Phase D timeline: surface the gateway's (simulated) rollback as a step event.
        if result.rollback_history:
            for rb in result.rollback_history:
                _exec_timeline.record(result.execution_id, rb.get("step_id", ""), "rollback",
                                      order=rb.get("order", 0), detail=rb)
        return result
    finally:
        if cleanup:
            adapter.close()


def _record_planned(plan_id: str, execution_id: str) -> None:
    try:
        from app.execution_planning import registry as plan_reg
        plan = plan_reg.get(plan_id)
        if plan is not None:
            for step in plan.steps:
                _exec_timeline.record(execution_id, step.step_id, "planned", order=step.order,
                                      detail={"action_type": step.action_type.value})
    except Exception:
        pass


def build_adapter(execution_id: str, *, headless: bool = True, mission_id: Optional[str] = None,
                  adaptive: bool = True, recovery: bool = True,
                  post_validation: bool = True) -> PlaywrightAdapter:
    return PlaywrightAdapter(execution_id=execution_id, headless=headless, mission_id=mission_id,
                             adaptive=adaptive, recovery=recovery, post_validation=post_validation)
