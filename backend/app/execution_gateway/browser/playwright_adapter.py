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
    ) -> None:
        self.execution_id    = execution_id or f"pw-{int(time.time()*1000)}"
        self.headless        = headless
        self.mission_id      = mission_id
        self.session_manager = session_manager or session_module
        # Internal transient-retry budget (reuses the EXISTING RetryEngine policy).
        self.retry_config    = retry_config or RetryConfig(max_retries=2)
        self.resolver        = resolver or element_resolver

    # ── adapter contract (9 methods) ──────────────────────────────────────────

    def navigate(self, command: ExecutionCommand) -> AdapterResult:
        return self._run(command, "navigate", self._do_navigate)

    def click(self, command: ExecutionCommand) -> AdapterResult:
        return self._run(command, "click", self._do_click)

    def type(self, command: ExecutionCommand) -> AdapterResult:
        return self._run(command, "type", self._do_type)

    def wait(self, command: ExecutionCommand) -> AdapterResult:
        return self._run(command, "wait", self._do_wait)

    def extract(self, command: ExecutionCommand) -> AdapterResult:
        return self._run(command, "extract", self._do_extract)

    def validate(self, command: ExecutionCommand) -> AdapterResult:
        return self._run(command, "validate", self._do_validate)

    def upload(self, command: ExecutionCommand) -> AdapterResult:
        return self._run(command, "upload", self._do_upload)

    def download(self, command: ExecutionCommand) -> AdapterResult:
        return self._run(command, "download", self._do_download)

    def execute_custom(self, command: ExecutionCommand) -> AdapterResult:
        return self._run(command, "custom", self._do_custom)

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

    # ── action implementations ────────────────────────────────────────────────

    def _do_navigate(self, session: Any, command: ExecutionCommand) -> dict:
        url = command.parameters.get("url") or command.target_description
        page = session.ensure_page()
        wait_until = command.parameters.get("wait_until", "load")
        page.goto(url, wait_until=wait_until)
        return {"url": page.url, "title": _safe(lambda: page.title()), "wait_until": wait_until}

    def _do_click(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        resolved = self.resolver.resolve(page, command.parameters)
        resolved.locator.click(timeout=self._timeout(command))
        return {"strategy": resolved.strategy, "value": resolved.value,
                "target": command.target_description}

    def _do_type(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        resolved = self.resolver.resolve(page, command.parameters)
        text = command.parameters.get("value") or command.parameters.get("text") or ""
        resolved.locator.fill(text, timeout=self._timeout(command))
        return {"strategy": resolved.strategy, "length": len(text)}

    def _do_wait(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        ms = int(command.parameters.get("timeout_ms", command.parameters.get("ms", 500)))
        if self.resolver.strategy_for(command.parameters):
            resolved = self.resolver.resolve(page, command.parameters)
            resolved.locator.wait_for(state=command.parameters.get("state", "visible"), timeout=ms)
            return {"waited_for": "element", "timeout_ms": ms}
        page.wait_for_timeout(ms)
        return {"waited_for": "duration", "waited_ms": ms}

    def _do_extract(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        mode = command.parameters.get("mode", "text").lower()  # text | html
        if self.resolver.strategy_for(command.parameters):
            resolved = self.resolver.resolve(page, command.parameters)
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
        if self.resolver.strategy_for(command.parameters):
            resolved = self.resolver.resolve(page, command.parameters)
            count = resolved.locator.count()
            return {"validate": "exists", "strategy": resolved.strategy, "count": count,
                    "_validation_passed": count > 0}
        return {"validate": "noop", "_validation_passed": True}

    def _do_upload(self, session: Any, command: ExecutionCommand) -> dict:
        page = session.ensure_page()
        resolved = self.resolver.resolve(page, command.parameters)
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
        resolved = self.resolver.resolve(page, command.parameters)
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
