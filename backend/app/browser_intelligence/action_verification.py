from __future__ import annotations

import time
from typing import Any

from app.browser_intelligence.models import ActionExpectation, BrowserStateModel, VerificationOutcome


class ActionVerificationEngine:
    """Declare and evaluate deterministic expected outcomes for browser actions."""

    def expectation_for(self, action: Any, state: BrowserStateModel) -> ActionExpectation:
        action_type = str(getattr(action, "action_type", "") or "")
        value = getattr(action, "value", None)
        target_selector = getattr(action, "target_selector", None)
        if action_type == "navigate":
            return ActionExpectation(
                action_type,
                {"url": value, "load_state": "domcontentloaded"},
                ("navigation_must_change_url_or_confirm_same_url",),
            )
        if action_type == "open_new_tab":
            return ActionExpectation(
                action_type,
                {"tab_count_delta": 1, "new_tab_url": value, "active_tab_url": value},
                ("must_not_duplicate_existing_tab",),
            )
        if action_type == "fill":
            return ActionExpectation(action_type, {"selector": target_selector, "value": value})
        if action_type == "click":
            return ActionExpectation(
                action_type,
                {"url_changed_or_dom_mutated_or_dialog_changed": True, "selector": target_selector},
                ("no_false_success_on_no_effect_click",),
            )
        if action_type == "upload":
            return ActionExpectation(action_type, {"file_attached": True, "selector": target_selector})
        if action_type == "download":
            return ActionExpectation(action_type, {"download_event": True, "completed": True})
        return ActionExpectation(action_type, {"observable_change_or_explicit_noop": True})

    def verify_state_transition(
        self,
        *,
        action_type: str,
        before: BrowserStateModel,
        after: BrowserStateModel,
        expected: dict[str, Any],
    ) -> VerificationOutcome:
        started = time.perf_counter()
        checks: list[dict[str, Any]] = []

        def record(name: str, passed: bool, detail: Any = None) -> None:
            checks.append({"check": name, "passed": bool(passed), "detail": detail})

        if expected.get("url"):
            record("expected_url", after.current_url == expected["url"], {"after": after.current_url})
        if expected.get("new_tab_url"):
            urls = [str(tab.get("url", "")) for tab in after.open_tabs]
            record("new_tab_url", expected["new_tab_url"] in urls or after.current_url == expected["new_tab_url"], {"urls": urls})
        if expected.get("tab_count_delta") is not None:
            delta = len(after.open_tabs) - len(before.open_tabs)
            record("tab_count_delta", delta >= int(expected["tab_count_delta"]), {"delta": delta})
        if expected.get("url_changed_or_dom_mutated_or_dialog_changed"):
            changed = (
                before.current_url != after.current_url
                or before.title != after.title
                or before.dialogs != after.dialogs
                or before.focused_element != after.focused_element
            )
            record("observable_change", changed)
        if not checks:
            record("default_observable", before.to_dict() != after.to_dict())

        verified = all(check["passed"] for check in checks)
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return VerificationOutcome(
            action_type=action_type,
            verified=verified,
            checks=checks,
            latency_ms=elapsed_ms,
            false_success_prevented=not verified,
        )

    def cross_validate(
        self,
        *,
        action_type: str,
        signals: dict[str, Any],
    ) -> VerificationOutcome:
        started = time.perf_counter()
        checks: list[dict[str, Any]] = []

        def record(name: str, passed: bool, detail: Any = None) -> None:
            checks.append({"check": name, "passed": bool(passed), "detail": detail})

        if action_type == "navigate":
            record("url", bool(signals.get("url_changed") or signals.get("expected_url")))
            record("title", bool(signals.get("title_changed") or signals.get("title_present")))
            record("dom", bool(signals.get("dom_changed") or signals.get("page_classification")))
            record("classification", bool(signals.get("page_classification")))
        elif action_type == "open_new_tab":
            record("tab_count", bool(signals.get("tab_count_increased")))
            record("active_tab", bool(signals.get("active_tab_url")))
            record("url", bool(signals.get("new_tab_url")))
        elif action_type == "upload":
            record("file_attached", bool(signals.get("file_attached")))
            record("dom_confirmation", bool(signals.get("filename_visible") or signals.get("status_text")))
            record("browser_event", bool(signals.get("upload_event")))
        elif action_type == "download":
            record("browser_event", bool(signals.get("download_event")))
            record("filesystem", bool(signals.get("file_exists")))
            record("completion", bool(signals.get("download_completed")))
        elif action_type == "search_result":
            record("adapter", bool(signals.get("adapter") in {"google_search", "bing_search"}))
            record("dom", bool(signals.get("open_selector") or signals.get("title")))
            record("external_url", bool(str(signals.get("url", "")).startswith(("http://", "https://"))))
        else:
            for key, value in signals.items():
                record(str(key), bool(value), value)

        verified = bool(checks) and sum(1 for check in checks if check["passed"]) >= max(1, len(checks) - 1)
        return VerificationOutcome(
            action_type=action_type,
            verified=verified,
            checks=checks,
            latency_ms=int((time.perf_counter() - started) * 1000),
            false_success_prevented=not verified,
        )
