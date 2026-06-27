"""
Phase C — Browser execution entrypoint.

Drives a real-browser execution through the EXISTING, UNCHANGED gateway API:

  1. gateway.start(plan_id, auto_run=False, retry_config=RetryConfig(max_retries=0))
       -> creates the ExecutionRecord (PENDING) and returns its execution_id
  2. build a PlaywrightAdapter bound to that execution_id (so its browser session is
       keyed by the real execution id, and the REST session/screenshot endpoints work)
  3. gateway.resume(execution_id, adapter=playwright_adapter)
       -> runs the plan through Dispatcher -> PlaywrightAdapter -> Browser

RetryConfig(max_retries=0) makes the runner do exactly one dispatch per step; the
PlaywrightAdapter is the browser-retry authority and retries transient errors itself.
No gateway / runner / retry-engine code is modified.
"""
from __future__ import annotations

from typing import Optional

from app.execution_gateway import engine as gateway
from app.execution_gateway.models import ExecutionRecord, RetryConfig
from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter


def execute_plan_with_browser(
    plan_id:   str,
    *,
    headless:  bool = True,
    cleanup:   bool = True,
) -> ExecutionRecord:
    """Execute a READY plan against a real browser via Playwright. Returns the record."""
    # Construct the adapter first so the record's adapter_name is recorded as
    # "playwright" at start time; bind the real execution_id before resume (the browser
    # session is created lazily on the first action, so binding after start is safe).
    adapter = PlaywrightAdapter(headless=headless)
    record = gateway.start(plan_id, auto_run=False, adapter=adapter,
                           retry_config=RetryConfig(max_retries=0))
    adapter.execution_id = record.execution_id
    adapter.mission_id = record.mission_id
    try:
        return gateway.resume(record.execution_id, adapter=adapter)
    finally:
        if cleanup:
            adapter.close()


def build_adapter(execution_id: str, *, headless: bool = True,
                  mission_id: Optional[str] = None) -> PlaywrightAdapter:
    return PlaywrightAdapter(execution_id=execution_id, headless=headless, mission_id=mission_id)
