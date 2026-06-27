"""
Phase C — PlaywrightAdapter (real browser execution).

Implements the EXISTING ExecutionAdapter contract (Phase B) — same 9 methods, same
AdapterResult. The Execution Gateway / Dispatcher / Runner / Retry / Validation /
Rollback engines are UNCHANGED; only the adapter is real.

Key design points:
  - The adapter NEVER owns Playwright objects directly — it asks the
    BrowserSessionManager (keyed by execution_id) for a live page.
  - Element resolution is deterministic (ElementResolver). No AI / OCR / self-healing.
  - The adapter is the browser-retry authority: it reuses the EXISTING Retry Engine to
    retry ONLY transient errors (timeout / detached / stale / temporary rendering).
    Non-retryable errors (missing element, invalid selector, auth) are never retried.
    Browser executions run the gateway runner with RetryConfig(max_retries=0) so the
    runner does not double-retry — see browser/run.py.
  - Every action returns success, duration, details, validation result, and an optional
    screenshot path inside the standard AdapterResult.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from app.execution_gateway import retry_engine
from app.execution_gateway.adapter import ExecutionAdapter
from app.execution_gateway.models import AdapterResult, ExecutionCommand, RetryConfig
from app.execution_gateway.browser import errors as browser_errors
from app.execution_gateway.browser import resolver as element_resolver
from app.execution_gateway.browser import session as session_module

# ── Phase D — Adaptive Execution & Recovery (additive; used only when enabled) ──
from app.execution_gateway.browser import adaptive_resolver as _adaptive_resolver
from app.execution_gateway.browser import failure_classes as _failure_classes
from app.execution_gateway.browser import recovery as _recovery_engine
from app.execution_gateway.browser import execution_validation as _exec_validation
from app.execution_gateway.browser import monitor as _exec_monitor
from app.execution_gateway.browser import metrics as _exec_metrics
from app.execution_gateway.browser import exec_timeline as _exec_timeline
from app.execution_gateway.browser.failure_classes import RecoveryAction


class PlaywrightAdapter(ExecutionAdapter):

    name = "playwright"

    def __init__(
        self,
        execution_id:    Optional[str] = None,
        *,
        headless:        bool = True,
        mission_id:      Optional[str] = None,
        session_manager: Any = None,
        retry_config:    Optional[RetryConfig] = None,
        resolver:        Any = None,
        # ── Phase D (additive, opt-in). All default OFF → Phase C byte-identical. ──
        adaptive:        bool = False,
        recovery:        bool = False,
        post_validation: bool = False,
        monitor:         Any = None,
        metrics:         Any = None,
        timeline:        Any = None,
    ) -> None:
        self.execution_id    = execution_id or f"pw-{int(time.time()*1000)}"
        self.headless        = headless
        self.mission_id      = mission_id
        self.session_manager = session_manager or session_module
        # Internal transient-retry budget (reuses the EXISTING RetryEngine policy).
        self.retry_config    = retry_config or RetryConfig(max_retries=2)
        self.resolver        = resolver or element_resolver
        # Phase D collaborators (only consulted when the matching flag is on).
        self.adaptive        = adaptive
        self.recovery        = recovery
        self.post_validation = post_validation
        self.phase_d         = adaptive or recovery or post_validation
        self.monitor         = monitor  if monitor  is not None else _exec_monitor
        self.metrics         = metrics  if metrics  is not None else _exec_metrics
        self.timeline        = timeline if timeline is not None else _exec_timeline

    # ── adapter contract (9 methods) ──────────────────────────────────────────

    def navigate(self, command: ExecutionCommand) -> AdapterResult:
        return self._execute(command, "navigate", self._do_navigate)

    def click(self, command: ExecutionCommand) -> AdapterResult:
        return self._execute(command, "click", self._do_click)

    def type(self, command: ExecutionCommand) -> AdapterResult:
        return self._execute(command, "type", self._do_type)

    def wait(self, command: ExecutionCommand) -> AdapterResult:
        return self._execute(command, "wait", self._do_wait)

    def extract(self, command: ExecutionCommand) -> AdapterResult:
        return self._execute(command, "extract", self._do_extract)

    def validate(self, command: ExecutionCommand) -> AdapterResult:
        return self._execute(command, "validate", self._do_validate)

    def upload(self, command: ExecutionCommand) -> AdapterResult:
        return self._execute(command, "upload", self._do_upload)

    def download(self, command: ExecutionCommand) -> AdapterResult:
        return self._execute(command, "download", self._do_download)

    def execute_custom(self, command: ExecutionCommand) -> AdapterResult:
        return self._execute(command, "custom", self._do_custom)

    # ── shared run wrapper: timing + transient retry + classification ──────────

    def _run(self, command: ExecutionCommand, phase: str, fn) -> AdapterResult:
        t0 = time.perf_counter()
        logs: list[str] = []
        attempt = 0
        while True:
            attempt += 1
            try:
                session = self.session_manager.get_or_create(self.execution_id, headless=self.headless)
                details = fn(session, command)
                validation_passed = bool(details.pop("_validation_passed", True))
                duration = (time.perf_counter() - t0) * 1000
                logs.append(f"[playwright] {phase} ok (attempt {attempt})")
                self._post_action(phase, session, command, details)
                screenshot = None
                if command.parameters.get("screenshot"):
                    screenshot = self._safe_screenshot(phase)
                return AdapterResult(
                    success=True,
                    duration_ms=round(duration, 3),
                    logs=logs,
                    output={
                        "details":           details,
                        "validation_result": validation_passed,
                        "screenshot_path":   screenshot,
                        "attempts":          attempt,
                        "phase":             phase,
                    },
                    validation_passed=validation_passed,
                    message="ok" if validation_passed else "validation mismatch",
                )
            except Exception as exc:  # noqa: BLE001 — classify, never crash the runner
                cls = browser_errors.classify(exc, during=phase)
                logs.append(f"[playwright] {phase} error {cls.error_type.value} (attempt {attempt})")
                # Transient recovery for detached/stale handles before retrying.
                if cls.error_type in (browser_errors.BrowserErrorType.detached_node,
                                      browser_errors.BrowserErrorType.stale_handle):
                    self._recover_page()
                if retry_engine.should_retry(attempt, self.retry_config,
                                             dispatch_failed=cls.retryable,
                                             validation_failed=False):
                    continue
                duration = (time.perf_counter() - t0) * 1000
                screenshot = self._safe_screenshot(f"{phase}-error")
                return AdapterResult(
                    success=False,
                    duration_ms=round(duration, 3),
                    logs=logs,
                    output={
                        "error":           cls.to_dict(),
                        "screenshot_path": screenshot,
                        "attempts":        attempt,
                        "phase":           phase,
                    },
                    validation_passed=False,
                    message=cls.message or cls.error_type.value,
                )

    # ── Phase D: adaptive execution path (used only when a Phase D flag is on) ──

    def _execute(self, command: ExecutionCommand, phase: str, fn) -> AdapterResult:
        if self.phase_d:
            return self._run_adaptive(command, phase, fn)
        return self._run(command, phase, fn)

    def _resolve(self, page: Any, params: dict):
        if self.adaptive:
            return _adaptive_resolver.resolve_strict(page, params)
        return self.resolver.resolve(page, params)

    def _strategy_for(self, params: dict):
        if self.adaptive:
            return _adaptive_resolver.strategy_for(params)
        return self.resolver.strategy_for(params)

    def _pre_state(self, session: Any) -> dict:
        state: dict = {}
        try:
            page = session.ensure_page()
            state["url"] = page.url
        except Exception:
            pass
        return state

    def _tl(self, step_id: str, event: str, order: int, detail: Optional[dict] = None) -> None:
        if self.timeline is None:
            return
        try:
            self.timeline.record(self.execution_id, step_id, event, order=order, detail=detail or {})
        except Exception:
            pass

    def _finish_monitor(self, rec, attempts, outcome, validation, category, strategy, recoveries, screenshots) -> None:
        if rec is None or self.monitor is None:
            return
        try:
            self.monitor.finish_step(
                rec, finished_at=time.time(), attempts=attempts, outcome=outcome,
                validation_result=validation, failure_category=category,
                locator_strategy=strategy, recovery_used=recoveries, screenshots=screenshots)
        except Exception:
            pass

    def _metric(self, fn_name: str, **kw) -> None:
        if self.metrics is None:
            return
        try:
            getattr(self.metrics, fn_name)(**kw)
        except Exception:
            pass

    def _run_adaptive(self, command: ExecutionCommand, phase: str, fn) -> AdapterResult:
        t0 = time.perf_counter()
        logs: list[str] = []
        attempt = 0
        recoveries_used: list[str] = []
        last_strategy: Optional[str] = None
        order = getattr(command, "order", 0)
        step_id = getattr(command, "step_id", "") or ""

        rec = None
        if self.monitor is not None:
            try:
                rec = self.monitor.start_step(self.execution_id, step_id, order, phase, time.time())
            except Exception:
                rec = None
        self._tl(step_id, "started", order)

        while True:
            attempt += 1
            session = None
            try:
                session = self.session_manager.get_or_create(self.execution_id, headless=self.headless)
                pre_state = self._pre_state(session) if self.post_validation else {}
                details = fn(session, command)
                action_validation = bool(details.pop("_validation_passed", True))
                last_strategy = details.get("strategy") or last_strategy
                self._post_action(phase, session, command, details)

                # First-class post-action validation (validate_after).
                post_pass = True
                post_detail = None
                if self.post_validation:
                    check = _exec_validation.validate(phase, session, command,
                                                      pre_state=pre_state, result_details=details)
                    if check.performed:
                        post_detail = check.to_dict()
                        post_pass = check.passed
                        self._metric("record_validation", passed=check.passed)
                        self._tl(step_id, "validated", order, {"passed": check.passed, "strategy": check.strategy})

                step_ok = action_validation and post_pass

                # Validation-failure recovery: re-read + retry (bounded by retry_config).
                if (not step_ok) and self.recovery and retry_engine.should_retry(
                        attempt, self.retry_config, dispatch_failed=True, validation_failed=False):
                    val_analysis = _failure_classes.classify_failure(ValueError("validation failed"), phase=phase)
                    rr = _recovery_engine.recover(val_analysis, session, command)
                    recoveries_used.extend(rr.actions)
                    self._metric("record_recovery", succeeded=rr.recovered)
                    if rr.actions:
                        self._tl(step_id, "recovered", order, rr.to_dict())
                    self._tl(step_id, "retried", order, {"reason": "validation"})
                    logs.append(f"[playwright] {phase} validation retry (attempt {attempt})")
                    continue

                duration = (time.perf_counter() - t0) * 1000
                outcome = "completed" if step_ok else "failed"
                self._tl(step_id, "completed" if step_ok else "failed", order)
                self._finish_monitor(rec, attempt, outcome, step_ok, None, last_strategy,
                                     recoveries_used, [])
                self._metric("record_step", succeeded=step_ok, retries=attempt - 1,
                             elapsed_ms=duration, locator_strategy=last_strategy)
                logs.append(f"[playwright] {phase} ok (attempt {attempt})")
                screenshot = self._safe_screenshot(phase) if command.parameters.get("screenshot") else None
                return AdapterResult(
                    success=True,
                    duration_ms=round(duration, 3),
                    logs=logs,
                    output={
                        "details":           details,
                        "validation_result": step_ok,
                        "post_validation":   post_detail,
                        "screenshot_path":   screenshot,
                        "attempts":          attempt,
                        "recoveries":        len(recoveries_used),
                        "recovery_used":     recoveries_used,
                        "locator_strategy":  last_strategy,
                        "phase":             phase,
                    },
                    validation_passed=step_ok,
                    message="ok" if step_ok else "validation mismatch",
                )

            except Exception as exc:  # noqa: BLE001 — classify, recover, never crash the runner
                analysis = _failure_classes.classify_failure(exc, phase=phase)
                category = analysis.category
                profile = analysis.profile
                logs.append(f"[playwright] {phase} {category.value} (attempt {attempt})")
                self._metric("record_failure", category=category.value)

                # Deterministic recovery (bounded) for retryable categories only.
                if self.recovery and profile.retryable and \
                        any(a != RecoveryAction.none for a in profile.recommended_recovery):
                    try:
                        rr = _recovery_engine.recover(analysis, session, command)
                        recoveries_used.extend(rr.actions)
                        self._metric("record_recovery", succeeded=rr.recovered)
                        if rr.actions:
                            self._tl(step_id, "recovered", order, rr.to_dict())
                    except Exception:
                        pass

                # Retry only when the failure class allows AND the budget remains.
                if profile.retryable and retry_engine.should_retry(
                        attempt, self.retry_config, dispatch_failed=True, validation_failed=False):
                    self._tl(step_id, "retried", order, {"category": category.value})
                    continue

                # Permanent failure OR budget exhausted → fail immediately.
                duration = (time.perf_counter() - t0) * 1000
                screenshot = self._safe_screenshot(f"{phase}-error")
                self._tl(step_id, "failed", order, {"category": category.value})
                self._finish_monitor(rec, attempt, "failed", False, category.value, last_strategy,
                                     recoveries_used, [screenshot] if screenshot else [])
                self._metric("record_step", succeeded=False, retries=attempt - 1,
                             elapsed_ms=duration, locator_strategy=last_strategy)
                return AdapterResult(
                    success=False,
                    duration_ms=round(duration, 3),
                    logs=logs,
                    output={
                        "error":            analysis.base.to_dict(),
                        "failure_category": category.value,
                        "failure_profile":  profile.to_dict(),
                        "screenshot_path":  screenshot,
                        "attempts":         attempt,
                        "recoveries":       len(recoveries_used),
                        "recovery_used":    recoveries_used,
                        "locator_strategy": last_strategy,
                        "phase":            phase,
                    },
                    validation_passed=False,
                    message=analysis.base.message or category.value,
                )

    # ── action implementations ────────────────────────────────────────────────

    def _do_navigate(self, session: Any, command: ExecutionCommand) -> dict:
        url = command.parameters.get("url") or command.target_description
        page = session.ensure_page()
        wait_until = command.parameters.get("wait_until", "load")
        page.goto(url, wait_until=wait_until)
        return {"url": page.url, "title": _safe(lambda: page.title()), "wait_until": wait_until}

    def _do_click(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        resolved = self._resolve(page, command.parameters)
        resolved.locator.click(timeout=self._timeout(command))
        return {"strategy": resolved.strategy, "value": resolved.value,
                "target": command.target_description}

    def _do_type(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        resolved = self._resolve(page, command.parameters)
        text = command.parameters.get("value") or command.parameters.get("text") or ""
        resolved.locator.fill(text, timeout=self._timeout(command))
        return {"strategy": resolved.strategy, "length": len(text)}

    def _do_wait(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        ms = int(command.parameters.get("timeout_ms", command.parameters.get("ms", 500)))
        if self._strategy_for(command.parameters):
            resolved = self._resolve(page, command.parameters)
            resolved.locator.wait_for(state=command.parameters.get("state", "visible"), timeout=ms)
            return {"waited_for": "element", "timeout_ms": ms}
        page.wait_for_timeout(ms)
        return {"waited_for": "duration", "waited_ms": ms}

    def _do_extract(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        mode = command.parameters.get("mode", "text").lower()  # text | html
        if self._strategy_for(command.parameters):
            resolved = self._resolve(page, command.parameters)
            content = resolved.locator.inner_html() if mode == "html" else resolved.locator.inner_text()
            strat = resolved.strategy
        else:
            content = page.content() if mode == "html" else page.inner_text("body")
            strat = "page"
        content = content or ""
        return {"mode": mode, "strategy": strat, "content_length": len(content),
                "content_preview": content[:500]}

    def _do_validate(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        strategy = (command.validation_strategy or command.parameters.get("strategy") or "").upper()
        if strategy in ("URL_MATCH", "VALIDATE_URL"):
            expected = command.parameters.get("expected_url") or command.expected_result or ""
            current = page.url
            passed = expected in current if expected else False
            return {"validate": "url", "expected": expected, "current": current,
                    "_validation_passed": passed}
        if strategy in ("TEXT_MATCH", "VALIDATE_TEXT"):
            expected = command.parameters.get("expected_text") or command.expected_result or ""
            body = _safe(lambda: page.inner_text("body")) or ""
            passed = expected in body if expected else False
            return {"validate": "text", "expected": expected, "_validation_passed": passed}
        # DOM_PRESENCE / VALIDATE_EXISTS / default
        if self._strategy_for(command.parameters):
            resolved = self._resolve(page, command.parameters)
            count = resolved.locator.count()
            return {"validate": "exists", "strategy": resolved.strategy, "count": count,
                    "_validation_passed": count > 0}
        return {"validate": "noop", "_validation_passed": True}

    def _do_upload(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        resolved = self._resolve(page, command.parameters)
        files = command.parameters.get("files")
        if not files:
            single = command.parameters.get("file")
            files = [single] if single else []
        if not files:
            raise ValueError("upload failed: no files provided")
        resolved.locator.set_input_files(files)
        return {"strategy": resolved.strategy, "files": files, "count": len(files)}

    def _do_download(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        resolved = self._resolve(page, command.parameters)
        with page.expect_download(timeout=self._timeout(command)) as dl_info:
            resolved.locator.click()
        download = dl_info.value
        path = _safe(lambda: str(download.path()))
        session.downloads.append(path or "")
        return {"strategy": resolved.strategy, "download_path": path,
                "suggested_filename": _safe(lambda: download.suggested_filename)}

    def _do_custom(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        action = command.parameters.get("action", "noop")
        if action == "scroll":
            dy = int(command.parameters.get("dy", 400))
            page.evaluate(f"window.scrollBy(0, {dy})")
            return {"custom": "scroll", "dy": dy}
        if action == "refresh":
            session.refresh()
            return {"custom": "refresh"}
        return {"custom": action}

    # ── side effects: runtime + browser sync (non-blocking, reuse existing) ────

    def _post_action(self, phase: str, session: Any, command: ExecutionCommand, details: dict) -> None:
        if phase not in ("navigate", "download", "upload", "custom"):
            return
        # Emit a V7.0 BrowserEvent (do not invent a new sync architecture).
        try:
            from app.browser import models as browser_models
            from app.browser import registry as browser_reg
            et = browser_models.BrowserEventType.page_loaded if phase == "navigate" \
                else browser_models.BrowserEventType.tab_updated
            ev = browser_models.make_event(
                et, getattr(session, "active_tab_id", "tab-0"),
                url=details.get("url"), title=details.get("title"),
                mission_id=self.mission_id,
                metadata={"phase": phase, "execution_id": self.execution_id},
            )
            browser_reg.register(ev)
        except Exception:
            pass
        # Update Runtime Context (reuse Runtime Layer; no redesign).
        try:
            if self.mission_id and phase == "navigate":
                from app.runtime import sync_service as rt_sync
                rt_sync.sync(active_mission_id=self.mission_id,
                             active_tab_id=getattr(session, "active_tab_id", "tab-0"),
                             last_url=details.get("url"), last_title=details.get("title"))
        except Exception:
            pass

    # ── helpers ────────────────────────────────────────────────────────────────

    def _timeout(self, command: ExecutionCommand) -> int:
        return int(command.parameters.get("timeout_ms", 30_000))

    def _recover_page(self) -> None:
        try:
            s = self.session_manager.get(self.execution_id)
            if s is not None:
                s.ensure_page()
        except Exception:
            pass

    def _safe_screenshot(self, label: str) -> Optional[str]:
        try:
            s = self.session_manager.get(self.execution_id)
            if s is not None:
                return s.screenshot(label)
        except Exception:
            pass
        return None

    def close(self) -> None:
        try:
            self.session_manager.close(self.execution_id)
        except Exception:
            pass


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None
