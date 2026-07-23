"""
Phase D — Execution Validation (first-class, additive).

After an action runs, optionally verify it actually succeeded — not just that the
dispatch did not raise. Expectations are declared per-step under
`command.parameters["validate_after"]` (a dict); when absent, validation is a no-op
(performed=False, passed=True) so existing plans are unaffected.

Supported post-action checks (deterministic — NO AI):
  url_contains      : substring present in page.url            (e.g. navigation/click)
  url_changed       : page.url differs from the pre-action url (e.g. click navigates)
  text_contains     : substring present in the page body text  (success message)
  text_absent       : substring NOT present in the page body
  exists            : a resolution-params dict resolves to >=1 element
  gone              : a resolution-params dict resolves to 0 elements (button disappears)
  value_equals      : a field's input value equals the expected string (TYPE)
  filename_visible  : a filename substring is present in the page body (UPLOAD)
  file_exists       : a local path (or the action's download_path) exists (DOWNLOAD)

Each sub-check is guarded; a check that errors counts as failed, never crashes.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from app.execution_gateway.browser import adaptive_resolver as _adaptive


@dataclass
class ValidationCheck:
    performed: bool
    passed:    bool
    strategy:  str                  # which post-action strategy ran ("none" if no-op)
    checks:    list[dict]           = field(default_factory=list)
    details:   dict[str, Any]       = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "performed": self.performed,
            "passed":    self.passed,
            "strategy":  self.strategy,
            "checks":    self.checks,
            "details":   self.details,
        }


class ExecutionValidator:

    def validate(
        self,
        phase:          str,
        session:        Any,
        command:        Any,
        *,
        pre_state:      Optional[dict] = None,
        result_details: Optional[dict] = None,
        resolver:       Any = None,
    ) -> ValidationCheck:
        params = getattr(command, "parameters", {}) or {}
        spec = params.get("validate_after")
        if not isinstance(spec, dict) or not spec:
            return ValidationCheck(performed=False, passed=True, strategy="none")

        resolver = resolver or _adaptive
        pre_state = pre_state or {}
        result_details = result_details or {}
        page = None
        try:
            page = session.ensure_page() if session is not None else None
        except Exception:
            page = None

        checks: list[dict] = []

        def _record(name: str, passed: bool, detail: Any = None) -> None:
            checks.append({"check": name, "passed": bool(passed), "detail": detail})

        # url_contains
        if "url_contains" in spec:
            expected = str(spec["url_contains"])
            current = _safe(lambda: page.url) or ""
            _record("url_contains", expected in current, {"expected": expected, "current": current})

        # url_changed
        if "url_changed" in spec and spec["url_changed"]:
            before = pre_state.get("url")
            current = _safe(lambda: page.url)
            _record("url_changed", before is not None and current is not None and current != before,
                    {"before": before, "after": current})

        # text_contains
        if "text_contains" in spec:
            expected = str(spec["text_contains"])
            body = _safe(lambda: page.inner_text("body")) or ""
            _record("text_contains", expected in body, {"expected": expected})

        # text_absent
        if "text_absent" in spec:
            absent = str(spec["text_absent"])
            body = _safe(lambda: page.inner_text("body")) or ""
            _record("text_absent", absent not in body, {"absent": absent})

        # exists
        if "exists" in spec and isinstance(spec["exists"], dict):
            cnt = self._count(resolver, page, spec["exists"])
            _record("exists", cnt is not None and cnt > 0, {"count": cnt})

        # gone (element disappeared)
        if "gone" in spec and isinstance(spec["gone"], dict):
            cnt = self._count(resolver, page, spec["gone"])
            _record("gone", cnt == 0, {"count": cnt})

        # value_equals (TYPE)
        if "value_equals" in spec:
            ve = spec["value_equals"]
            if isinstance(ve, dict):
                target_params = {k: v for k, v in ve.items() if k != "value"}
                expected = str(ve.get("value", ""))
            else:
                target_params = params
                expected = str(ve)
            actual = self._input_value(resolver, page, target_params)
            _record("value_equals", actual == expected, {"expected": expected, "actual": actual})

        # filename_visible (UPLOAD)
        if "filename_visible" in spec:
            fname = os.path.basename(str(spec["filename_visible"]))
            body = _safe(lambda: page.inner_text("body")) or ""
            _record("filename_visible", fname in body, {"filename": fname})

        # file_exists (DOWNLOAD)
        if "file_exists" in spec:
            fe = spec["file_exists"]
            path = result_details.get("download_path") if fe is True else str(fe)
            exists = bool(path) and _safe(lambda: os.path.exists(path)) is True
            _record("file_exists", exists, {"path": path})

        performed = len(checks) > 0
        passed = all(c["passed"] for c in checks) if performed else True
        strategy = "+".join(c["check"] for c in checks) if performed else "none"
        return ValidationCheck(performed=performed, passed=passed, strategy=strategy, checks=checks)

    # ── helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _count(resolver: Any, page: Any, rparams: dict) -> Optional[int]:
        try:
            if not resolver.strategy_for(rparams):
                return None
            resolved = resolver.resolve(page, rparams)
            return int(resolved.locator.count())
        except Exception:
            return None

    @staticmethod
    def _input_value(resolver: Any, page: Any, rparams: dict) -> Optional[str]:
        try:
            if not resolver.strategy_for(rparams):
                return None
            resolved = resolver.resolve(page, rparams)
            return resolved.locator.input_value()
        except Exception:
            try:
                resolved = resolver.resolve(page, rparams)
                return resolved.locator.inner_text()
            except Exception:
                return None


def _safe(fn):
    try:
        return fn()
    except Exception:
        return None


# ── Module-level singleton ────────────────────────────────────────────────────

_validator = ExecutionValidator()


def validate(phase: str, session: Any, command: Any, **kwargs) -> ValidationCheck:
    return _validator.validate(phase, session, command, **kwargs)
