"""
M0 — Test doubles (used by validate_m0.py and the pytest suite).

A FakeDriver implements the Driver interface over a scripted list of page snapshots, and a
FakeAnalyzeClient returns scripted actions. These let the entire TaskRunner loop, metrics,
and reports be exercised with no browser and no network. Test-only — never imported by the
live run path (m0_runner uses the real PlaywrightDriver + AnalyzeClient).
"""
from __future__ import annotations

from typing import Callable, Optional

from benchmark.m0_executor import Driver, ExecResult
from benchmark.m0_models import LocatorStrategy
from benchmark.analyze_client import AnalyzeResult, SuggestedActionDTO


def page(url: str, *, text: str = "", elements: Optional[list[dict]] = None,
         title: str = "Fake") -> dict:
    return {
        "url": url, "title": title, "metadata": {},
        "interactive_elements": elements or [], "content_blocks": [],
        "headings": [], "selected_text": "", "visible_text": text, "images": [],
    }


class FakeDriver(Driver):
    """Scripted driver. Advances to the next page whenever an executed action succeeds."""

    def __init__(self, pages: list[dict], *, responder: Optional[Callable] = None,
                 captcha: bool = False, nav_status: int = 200) -> None:
        assert pages, "FakeDriver needs at least one page"
        self._pages = pages
        self._i = 0
        self._responder = responder
        self._captcha = captcha
        self._status = nav_status
        self._url = pages[0].get("url", "")
        self.navigations: list[str] = []
        self.screenshots_taken = 0

    def navigate(self, url: str) -> None:
        self.navigations.append(url)
        self._url = url

    def current_url(self) -> str:
        return self._pages[self._i].get("url", self._url)

    def last_navigation_status(self) -> Optional[int]:
        return self._status

    def capture(self) -> dict:
        return self._pages[self._i]

    def screenshot(self, path: str) -> Optional[str]:
        self.screenshots_taken += 1
        return None  # don't touch disk in tests

    def element_present(self, selector: str) -> bool:
        pg = self._pages[self._i]
        sels = [e.get("selector", "") for e in pg.get("interactive_elements", [])]
        return any(selector in s or s == selector for s in sels) or selector in pg.get("visible_text", "")

    def wait_stable(self, max_ms: int = 3000) -> None:
        pass

    def detect_captcha(self) -> bool:
        return self._captcha

    def execute_playwright(self, action: dict) -> ExecResult:
        return self._exec(action)

    def execute_synthetic(self, action: dict) -> ExecResult:
        return self._exec(action)

    def _exec(self, action: dict) -> ExecResult:
        if self._responder is not None:
            res = self._responder(action, self._i)
        else:
            res = ExecResult(True, "ok", locator_strategy=LocatorStrategy.css_selector.value,
                             locator_attempts=1)
        if res.success and self._i < len(self._pages) - 1:
            self._i += 1
        return res


class FakeAnalyzeClient:
    """Returns scripted actions. `script` is a list of (action_type, selector, value) or None."""

    def __init__(self, script: list, analysis: str = "") -> None:
        self._script = script
        self._n = 0
        self._analysis = analysis

    def analyze(self, *, session_id: str, task: str, page_context: dict,
                prior_steps: list) -> AnalyzeResult:
        if self._n >= len(self._script):
            return AnalyzeResult(analysis=self._analysis, suggested_actions=[])
        spec = self._script[self._n]
        self._n += 1
        if spec is None:
            return AnalyzeResult(analysis=self._analysis, suggested_actions=[])
        atype, selector, value = spec
        action = SuggestedActionDTO(
            action_id=f"a{self._n}", action_type=atype, target_selector=selector,
            value=value, description=f"{atype} {selector}", reasoning="", confidence=0.9,
            safety_level="safe")
        return AnalyzeResult(analysis=self._analysis, suggested_actions=[action],
                             prompt_tokens=1000, completion_tokens=120)
