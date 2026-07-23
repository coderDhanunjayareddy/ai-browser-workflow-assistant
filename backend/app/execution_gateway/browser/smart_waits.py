from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


DEFAULT_SMART_WAIT_TIMEOUT_MS = 5_000
POLL_INTERVAL_MS = 100


@dataclass(frozen=True)
class SmartWaitResult:
    ready: bool
    reason: str
    duration_ms: float
    signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "reason": self.reason,
            "duration_ms": round(self.duration_ms, 3),
            "signals": dict(self.signals),
        }


def wait_for_ready(page: Any, *, timeout_ms: int = DEFAULT_SMART_WAIT_TIMEOUT_MS) -> SmartWaitResult:
    start = time.perf_counter()
    deadline = time.perf_counter() + max(0, timeout_ms) / 1000
    first_signature = _safe_signature(page)
    last_signature = first_signature
    stable_ticks = 0
    overlays = 0

    while time.perf_counter() <= deadline:
        state = _page_state(page)
        overlays = int(state.get("overlay_count", 0))
        current_signature = state.get("signature")
        if state.get("ready_state") in {"interactive", "complete"} and overlays == 0:
            if current_signature == last_signature:
                stable_ticks += 1
            else:
                stable_ticks = 0
                last_signature = current_signature
            if stable_ticks >= 2:
                return _result(True, "dom_stable", start, first_signature, current_signature, overlays)
        _wait(page, POLL_INTERVAL_MS)

    state = _page_state(page)
    return _result(False, "timeout", start, first_signature, state.get("signature"), int(state.get("overlay_count", 0)))


def wait_for_selector_state(page: Any, selector: str, *, state: str = "visible", timeout_ms: int = DEFAULT_SMART_WAIT_TIMEOUT_MS) -> SmartWaitResult:
    start = time.perf_counter()
    try:
        locator = page.locator(selector)
        locator.wait_for(state=state, timeout=timeout_ms)
        return SmartWaitResult(
            ready=True,
            reason=f"selector_{state}",
            duration_ms=(time.perf_counter() - start) * 1000,
            signals={"selector": selector, "state": state},
        )
    except Exception as exc:  # noqa: BLE001
        return SmartWaitResult(
            ready=False,
            reason="selector_timeout",
            duration_ms=(time.perf_counter() - start) * 1000,
            signals={"selector": selector, "state": state, "error": str(exc)[:200]},
        )


def _page_state(page: Any) -> dict[str, Any]:
    try:
        return page.evaluate(
            """() => {
              const visible = (el) => {
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
              };
              const overlays = Array.from(document.querySelectorAll(
                '[aria-modal="true"], [role="dialog"], dialog, .modal, [class*="toast"], [class*="snackbar"]'
              )).filter(visible).length;
              const interactive = document.querySelectorAll(
                'a[href], button, input, textarea, select, [role="button"], [role="link"], [contenteditable="true"]'
              ).length;
              const textLen = (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').trim().length;
              return {
                ready_state: document.readyState,
                overlay_count: overlays,
                signature: [location.href, document.title, textLen, interactive, overlays].join('|')
              };
            }"""
        )
    except Exception:
        return {"ready_state": "unknown", "overlay_count": 0, "signature": _safe_signature(page)}


def _safe_signature(page: Any) -> str:
    try:
        return "|".join([str(page.url), str(page.title())])
    except Exception:
        return ""


def _wait(page: Any, ms: int) -> None:
    try:
        page.wait_for_timeout(ms)
    except Exception:
        time.sleep(ms / 1000)


def _result(ready: bool, reason: str, start: float, first_signature: str, final_signature: Any, overlays: int) -> SmartWaitResult:
    return SmartWaitResult(
        ready=ready,
        reason=reason,
        duration_ms=(time.perf_counter() - start) * 1000,
        signals={
            "initial_signature": first_signature,
            "final_signature": str(final_signature or ""),
            "overlay_count": overlays,
        },
    )
