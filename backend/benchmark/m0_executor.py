"""
M0 — Browser driver + executors + page capture.

Defines the Driver interface the TaskRunner depends on, and the PlaywrightDriver that
implements it against a real Chromium. Two execution modes share one driver:
  • Mode A (playwright): trusted CDP input via the Playwright API, with a ranked locator
    ladder (data-testid > aria-label > css > text > xpath) — records which rung resolved.
  • Mode B (synthetic): injects the verbatim extension executor_v2 logic
    (injected_scripts.js -> window.__m0Execute__) — exactly what users run today.

Page capture always injects the verbatim extractor_v2 logic (window.__m0Extract__) so the
backend receives the EXACT production DOM snapshot in both modes.

`playwright` is imported lazily; this module imports fine without it (unit tests use a
FakeDriver that implements the same interface).
"""
from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from benchmark.m0_models import LocatorStrategy

_HERE = os.path.dirname(os.path.abspath(__file__))
_INJECT_PATH = os.path.join(_HERE, "injected_scripts.js")


def injected_js() -> str:
    with open(_INJECT_PATH, "r", encoding="utf-8") as f:
        return f.read()


@dataclass
class ExecResult:
    success:          bool
    message:          str = ""
    locator_strategy: Optional[str] = None
    locator_attempts: int = 0
    error_type:       str = ""


# captcha / challenge markers used for fast in-loop block detection
_CAPTCHA_DETECT = re.compile(
    r"(captcha|recaptcha|hcaptcha|i'?m not a robot|verify you are human|cf-challenge|"
    r"unusual traffic|are you a robot|security check)", re.IGNORECASE)


class Driver(ABC):
    """The browser surface the TaskRunner uses. Mode-independent."""

    @abstractmethod
    def navigate(self, url: str) -> None: ...

    @abstractmethod
    def current_url(self) -> str: ...

    @abstractmethod
    def capture(self) -> dict:
        """Return a PageContext-shaped dict via the injected production extractor."""

    @abstractmethod
    def screenshot(self, path: str) -> Optional[str]: ...

    @abstractmethod
    def element_present(self, selector: str) -> bool: ...

    @abstractmethod
    def wait_stable(self, max_ms: int = 3000) -> None: ...

    @abstractmethod
    def detect_captcha(self) -> bool: ...

    def last_navigation_status(self) -> Optional[int]:
        """HTTP status of the most recent top-level navigation, if known."""
        return None

    @abstractmethod
    def execute_playwright(self, action: dict) -> ExecResult: ...

    @abstractmethod
    def execute_synthetic(self, action: dict) -> ExecResult: ...

    def close(self) -> None:  # pragma: no cover - overridden
        pass


# ── Playwright implementation ───────────────────────────────────────────────-

class PlaywrightDriver(Driver):
    """Real Chromium. Construct via PlaywrightDriver.launch(...) as a context manager."""

    def __init__(self, page, context, browser, pw, upload_file: Optional[str] = None) -> None:
        self._page = page
        self._context = context
        self._browser = browser
        self._pw = pw
        self._upload_file = upload_file
        self._last_status: Optional[int] = None

    # -- lifecycle --------------------------------------------------------------
    @classmethod
    def launch(cls, *, headless: bool = True, storage_state: Optional[str] = None,
               upload_file: Optional[str] = None) -> "PlaywrightDriver":
        from playwright.sync_api import sync_playwright  # lazy
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        ctx_kwargs = {
            "viewport": {"width": 1366, "height": 900},
            "user_agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
        }
        if storage_state and os.path.exists(storage_state):
            ctx_kwargs["storage_state"] = storage_state
        context = browser.new_context(**ctx_kwargs)
        context.add_init_script(injected_js())
        page = context.new_page()
        return cls(page, context, browser, pw, upload_file=upload_file)

    def close(self) -> None:
        try:
            self._context.close()
            self._browser.close()
        finally:
            self._pw.stop()

    # -- observation ------------------------------------------------------------
    def navigate(self, url: str) -> None:
        resp = self._page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        self._last_status = resp.status if resp is not None else None

    def current_url(self) -> str:
        return self._page.url

    def last_navigation_status(self) -> Optional[int]:
        return self._last_status

    def capture(self) -> dict:
        # ensure the injected globals exist even if add_init_script was bypassed
        self._page.evaluate(f"() => {{ if (!window.__m0Extract__) {{ {injected_js()} }} }}")
        return self._page.evaluate("() => window.__m0Extract__()")

    def screenshot(self, path: str) -> Optional[str]:
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            self._page.screenshot(path=path, full_page=False)
            return path
        except Exception:
            return None

    def element_present(self, selector: str) -> bool:
        try:
            return self._page.locator(selector).count() > 0
        except Exception:
            return False

    def wait_stable(self, max_ms: int = 3000) -> None:
        try:
            self._page.wait_for_load_state("networkidle", timeout=max_ms)
        except Exception:
            pass

    def detect_captcha(self) -> bool:
        try:
            text = self._page.evaluate("() => document.body ? document.body.innerText.slice(0, 4000) : ''")
        except Exception:
            return False
        return bool(_CAPTCHA_DETECT.search(text or ""))

    # -- Mode B: synthetic (verbatim extension executor) ------------------------
    def execute_synthetic(self, action: dict) -> ExecResult:
        try:
            self._page.evaluate(f"() => {{ if (!window.__m0Execute__) {{ {injected_js()} }} }}")
            res = self._page.evaluate("(a) => window.__m0Execute__(a)", action)
            return ExecResult(success=bool(res.get("success")), message=res.get("message", ""),
                              locator_strategy=LocatorStrategy.css_selector.value, locator_attempts=1)
        except Exception as e:
            return ExecResult(False, f"synthetic eval error: {e}", error_type=type(e).__name__)

    # -- Mode A: Playwright trusted input ---------------------------------------
    def execute_playwright(self, action: dict) -> ExecResult:
        atype = action.get("action_type", "")
        value = action.get("value")
        selector = action.get("target_selector") or ""
        try:
            if atype == "navigate":
                if not value:
                    return ExecResult(False, "navigate: no url")
                self._page.goto(value, wait_until="domcontentloaded", timeout=45_000)
                return ExecResult(True, f"navigated {value}", locator_strategy=None, locator_attempts=0)
            if atype == "wait":
                self._page.wait_for_timeout(float(value or 2000))
                return ExecResult(True, "waited", locator_attempts=0)
            if atype == "scroll":
                delta = -600 if str(value or "down").lower() == "up" else 600
                self._page.mouse.wheel(0, delta)
                return ExecResult(True, "scrolled", locator_attempts=0)
            if atype == "keyboard_shortcut":
                self._page.keyboard.press(_pw_key(value))
                return ExecResult(True, f"pressed {value}", locator_attempts=0)

            # element-targeted actions use the ranked locator ladder
            locator, strategy, attempts = self._resolve(selector, action.get("description", ""), value)
            if locator is None:
                return ExecResult(False, f"all locator strategies failed for {selector!r}",
                                  locator_strategy=None, locator_attempts=attempts)

            if atype == "click" or atype == "choose_date":
                locator.scroll_into_view_if_needed(timeout=4000)
                locator.click(timeout=6000)
            elif atype == "fill":
                if self._is_file_input(locator):
                    if not self._upload_file:
                        return ExecResult(False, "no upload file configured",
                                          locator_strategy=strategy.value, locator_attempts=attempts)
                    locator.set_input_files(self._upload_file)
                else:
                    locator.fill(value or "", timeout=6000)
            elif atype == "select_option":
                try:
                    locator.select_option(value=value, timeout=4000)
                except Exception:
                    locator.select_option(label=value, timeout=4000)
            elif atype == "hover":
                locator.hover(timeout=6000)
            else:
                return ExecResult(False, f"unsupported action_type {atype}",
                                  locator_strategy=strategy.value, locator_attempts=attempts)
            return ExecResult(True, f"{atype} ok", locator_strategy=strategy.value, locator_attempts=attempts)
        except Exception as e:
            return ExecResult(False, f"{atype} error: {e}", error_type=type(e).__name__)

    # -- locator ladder ---------------------------------------------------------
    def _resolve(self, selector: str, description: str, value):
        """Try ranked strategies; return (locator, LocatorStrategy, attempts_count)."""
        attempts = 0
        for strategy, builder in self._ladder(selector, description, value):
            attempts += 1
            try:
                loc = builder()
                if loc is not None and loc.count() > 0:
                    return loc.first, strategy, attempts
            except Exception:
                continue
        return None, None, attempts

    def _ladder(self, selector: str, description: str, value):
        page = self._page
        out = []
        testid = _attr_from_selector(selector, "data-testid")
        if testid:
            out.append((LocatorStrategy.data_testid, lambda t=testid: page.get_by_test_id(t)))
        aria = _attr_from_selector(selector, "aria-label")
        if aria:
            out.append((LocatorStrategy.aria_label, lambda a=aria: page.get_by_label(a)))
        if selector and not selector.startswith("//"):
            out.append((LocatorStrategy.css_selector, lambda s=selector: page.locator(s)))
        needle = (description or "").strip() or (value or "")
        if needle:
            out.append((LocatorStrategy.text_match, lambda n=needle: page.get_by_text(n, exact=False)))
        if selector.startswith("//"):
            out.append((LocatorStrategy.xpath, lambda s=selector: page.locator(f"xpath={s}")))
        return out

    def _is_file_input(self, locator) -> bool:
        try:
            return locator.evaluate("el => el.tagName === 'INPUT' && el.type === 'file'")
        except Exception:
            return False


def _attr_from_selector(selector: str, attr: str) -> Optional[str]:
    m = re.search(rf'{re.escape(attr)}="([^"]+)"', selector or "")
    return m.group(1) if m else None


def _pw_key(value) -> str:
    """Map a human key name to a Playwright key chord."""
    if not value:
        return "Enter"
    v = str(value).strip()
    return {"enter": "Enter", "tab": "Tab", "escape": "Escape", "esc": "Escape"}.get(v.lower(), v)
