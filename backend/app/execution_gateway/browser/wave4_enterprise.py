from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


@dataclass(frozen=True)
class AdapterProfile:
    key: str
    capability_id: str
    domains: tuple[str, ...]
    selectors: tuple[str, ...]
    workflows: tuple[str, ...]
    optimizations: tuple[str, ...]
    recovery_hints: tuple[str, ...]


@dataclass(frozen=True)
class Wave4Result:
    capability_id: str
    success: bool
    duration_ms: float
    details: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "success": self.success,
            "duration_ms": round(self.duration_ms, 3),
            "details": dict(self.details),
            "error": self.error,
        }


ADAPTERS: dict[str, AdapterProfile] = {
    "google_workspace": AdapterProfile(
        "google_workspace",
        "browser.adapters.google_workspace",
        ("docs.google.com", "drive.google.com", "mail.google.com"),
        ("[role='textbox']", "[aria-label*='Search']", "[aria-label*='Compose']", "[data-tooltip]", ".docs-texteventtarget-iframe"),
        ("docs_edit", "sheets_table_navigation", "drive_preview", "gmail_compose"),
        ("rich_text", "large_tables", "virtualized_ui", "preview_dialogs"),
        ("search_by_aria_label", "fallback_to_keyboard_shortcuts", "detect_blocking_dialogs"),
    ),
    "microsoft365": AdapterProfile(
        "microsoft365",
        "browser.adapters.microsoft365",
        ("office.com", "microsoft365.com", "live.com", "outlook.office.com", "sharepoint.com"),
        ("[role='textbox']", "[aria-label*='Search']", "[aria-label*='New']", "[data-automationid]", ".ms-Button"),
        ("word_edit", "excel_grid_navigation", "outlook_compose", "onedrive_preview"),
        ("rich_text", "large_tables", "enterprise_dashboards", "preview_dialogs"),
        ("prefer_automationid", "fallback_to_ribbon_search", "detect_auth_frames"),
    ),
    "github_advanced": AdapterProfile(
        "github_advanced",
        "browser.adapters.github_advanced",
        ("github.com", "github.dev"),
        ("[data-testid]", "[aria-label]", ".js-navigation-item", ".react-code-text", ".cm-editor", ".monaco-editor"),
        ("pull_request_review", "code_search", "issue_triage", "web_editor"),
        ("code_editors", "keyboard_navigation", "virtualized_files"),
        ("prefer_data_testid", "recover_by_aria_label", "validate_repository_context"),
    ),
    "jira": AdapterProfile(
        "jira",
        "browser.adapters.jira",
        ("atlassian.net", "jira.com"),
        ("[data-testid]", "[aria-label]", "[role='dialog']", "[contenteditable='true']"),
        ("issue_search", "issue_update", "board_move", "comment"),
        ("virtualized_ui", "rich_text", "drag_drop", "complex_navigation"),
        ("prefer_data_testid", "handle_atlassian_dialogs", "recover_from_drawers"),
    ),
    "confluence": AdapterProfile(
        "confluence",
        "browser.adapters.confluence",
        ("atlassian.net", "confluence.com"),
        ("[data-testid]", "[contenteditable='true']", "[aria-label]", "[role='dialog']"),
        ("page_edit", "comment", "search", "file_preview"),
        ("rich_text", "file_preview", "complex_navigation"),
        ("prefer_data_testid", "detect_editor_mode", "recover_from_publish_dialog"),
    ),
    "slack": AdapterProfile(
        "slack",
        "browser.adapters.slack",
        ("slack.com",),
        ("[data-qa]", "[role='textbox']", "[aria-label]", ".ql-editor"),
        ("message_compose", "channel_search", "file_preview", "thread_reply"),
        ("rich_text", "virtualized_ui", "file_preview"),
        ("prefer_data_qa", "validate_channel_context", "no_duplicate_messages"),
    ),
    "notion": AdapterProfile(
        "notion",
        "browser.adapters.notion",
        ("notion.so", "notion.site"),
        ("[contenteditable='true']", "[data-block-id]", "[role='button']", "[aria-label]"),
        ("page_edit", "database_update", "search", "file_preview"),
        ("rich_text", "virtualized_ui", "large_tables"),
        ("recover_by_block_id", "keyboard_first_navigation", "validate_block_context"),
    ),
    "figma": AdapterProfile(
        "figma",
        "browser.adapters.figma",
        ("figma.com",),
        ("canvas", "[data-testid]", "[aria-label]", "[role='button']"),
        ("canvas_select", "comment", "file_navigation", "presentation"),
        ("canvas", "visual_regions", "complex_navigation"),
        ("coordinate_validation", "prefer_data_testid", "detect_modal_tools"),
    ),
    "canva": AdapterProfile(
        "canva",
        "browser.adapters.canva",
        ("canva.com",),
        ("canvas", "[data-testid]", "[aria-label]", "[role='button']"),
        ("design_edit", "asset_preview", "presentation", "export_dialog"),
        ("canvas", "file_preview", "visual_regions"),
        ("coordinate_validation", "detect_export_dialogs", "prefer_aria_label"),
    ),
    "salesforce": AdapterProfile(
        "salesforce",
        "browser.adapters.salesforce",
        ("salesforce.com", "force.com", "lightning.force.com"),
        ("[data-aura-class]", "[data-target-selection-name]", "[aria-label]", "[role='button']", "lightning-input"),
        ("record_search", "record_update", "dashboard_navigation", "report_filter"),
        ("enterprise_dashboards", "large_tables", "complex_navigation"),
        ("prefer_lightning_metadata", "detect_console_tabs", "validate_record_context"),
    ),
}


AUTH_CAPABILITY_ID = "browser.auth.enterprise_sso"
MFA_CAPABILITY_ID = "browser.auth.mfa_otp_handoff"
FILE_CAPABILITY_ID = "browser.enterprise_file_workflows"
OPTIMIZATION_CAPABILITY_ID = "browser.site_optimization.framework"


def parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return dict(parsed) if isinstance(parsed, dict) else {"text": raw}
        except json.JSONDecodeError:
            return {"text": raw}
    return {}


def adapter_for_url(url: str) -> AdapterProfile | None:
    host = urlparse(url).netloc.lower()
    return next(
        (profile for profile in ADAPTERS.values() if any(host == domain or host.endswith(f".{domain}") for domain in profile.domains)),
        None,
    )


def adapter_profile(adapter_key: str) -> AdapterProfile | None:
    return ADAPTERS.get(adapter_key)


def execute_site_adapter(page: Any, payload: dict[str, Any]) -> Wave4Result:
    start = time.perf_counter()
    requested = str(payload.get("adapter") or payload.get("site") or "").lower()
    profile = adapter_profile(requested) if requested else adapter_for_url(str(getattr(page, "url", "")))
    if profile is None:
        return _result("browser.adapters.unknown", False, start, {"requested": requested}, "adapter_not_found")
    try:
        state = page.evaluate(
            """(selectors) => {
              const visible = (node) => {
                const rect = node.getBoundingClientRect?.();
                const style = window.getComputedStyle?.(node);
                return !rect || (rect.width > 0 && rect.height > 0 && style?.display !== 'none' && style?.visibility !== 'hidden');
              };
              const counts = {};
              for (const selector of selectors) {
                try { counts[selector] = Array.from(document.querySelectorAll(selector)).filter(visible).length; }
                catch { counts[selector] = -1; }
              }
              const text = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 500);
              return {
                title: document.title,
                url: location.href,
                selector_counts: counts,
                visible_text_length: (document.body?.innerText || '').length,
                auth_signals: /sign in|single sign|sso|verify|code|authenticator|password/i.test(text),
                dialog_count: document.querySelectorAll('[role="dialog"], dialog, [aria-modal="true"]').length,
              };
            }""",
            list(profile.selectors),
        )
        selector_counts = dict(state.get("selector_counts") or {})
        discovered = sum(max(0, int(v)) for v in selector_counts.values())
        return _result(profile.capability_id, True, start, {
            "adapter": profile.key,
            "workflows": list(profile.workflows),
            "optimizations": list(profile.optimizations),
            "recovery_hints": list(profile.recovery_hints),
            "selector_counts": selector_counts,
            "discovered_elements": discovered,
            "auth_signals": bool(state.get("auth_signals")),
            "dialog_count": int(state.get("dialog_count") or 0),
            "url": state.get("url"),
            "title": state.get("title"),
        })
    except Exception as exc:  # noqa: BLE001
        return _result(profile.capability_id, False, start, {"adapter": profile.key}, str(exc)[:200])


def execute_sso_auth(page: Any, payload: dict[str, Any]) -> Wave4Result:
    start = time.perf_counter()
    try:
        state = _auth_state(page, payload)
        success = bool(state.get("sso_detected") or state.get("oauth_detected") or state.get("session_reuse_possible"))
        return _result(AUTH_CAPABILITY_ID, success, start, state, None if success else "sso_not_detected")
    except Exception as exc:  # noqa: BLE001
        return _result(AUTH_CAPABILITY_ID, False, start, {}, str(exc)[:200])


def execute_mfa_handoff(page: Any, payload: dict[str, Any]) -> Wave4Result:
    start = time.perf_counter()
    try:
        state = _auth_state(page, payload)
        success = bool(state.get("mfa_detected") or state.get("otp_detected"))
        state["handoff_required"] = success
        state["automation_boundary"] = "human_otp_required"
        return _result(MFA_CAPABILITY_ID, success, start, state, None if success else "mfa_not_detected")
    except Exception as exc:  # noqa: BLE001
        return _result(MFA_CAPABILITY_ID, False, start, {}, str(exc)[:200])


def execute_enterprise_file_workflow(page: Any, payload: dict[str, Any]) -> Wave4Result:
    start = time.perf_counter()
    workflow = str(payload.get("workflow") or "detect")
    try:
        state = page.evaluate(
            """(workflow) => {
              const selector = 'input[type=file], [aria-label*="Upload" i], [aria-label*="Download" i], [data-testid*="upload" i], [data-testid*="download" i], a[download], [role=dialog]';
              const elements = Array.from(document.querySelectorAll(selector));
              const labels = elements.slice(0, 20).map((node) => node.getAttribute('aria-label') || node.getAttribute('data-testid') || node.textContent || node.tagName);
              return {
                workflow,
                candidate_count: elements.length,
                labels,
                dialog_count: document.querySelectorAll('[role="dialog"], dialog, [aria-modal="true"]').length,
              };
            }""",
            workflow,
        )
        success = int(state.get("candidate_count") or 0) > 0 or workflow == "detect"
        return _result(FILE_CAPABILITY_ID, success, start, dict(state))
    except Exception as exc:  # noqa: BLE001
        return _result(FILE_CAPABILITY_ID, False, start, {"workflow": workflow}, str(exc)[:200])


def execute_site_optimization(page: Any, payload: dict[str, Any]) -> Wave4Result:
    start = time.perf_counter()
    profile = adapter_profile(str(payload.get("adapter") or payload.get("site") or "").lower()) or adapter_for_url(str(getattr(page, "url", "")))
    try:
        state = page.evaluate(
            """() => ({
              contenteditable_count: document.querySelectorAll('[contenteditable=true], [contenteditable="true"]').length,
              table_count: document.querySelectorAll('table, [role=grid], [role=table]').length,
              virtual_signals: document.querySelectorAll('[style*="transform: translate"], [data-virtualized], [aria-rowcount]').length,
              dashboard_signals: document.querySelectorAll('canvas, svg, [class*=chart], [class*=dashboard]').length,
              navigation_count: document.querySelectorAll('nav, [role=navigation], [aria-label*=Navigation i]').length,
            })"""
        )
        recommendations = _recommendations(dict(state), profile)
        return _result(OPTIMIZATION_CAPABILITY_ID, True, start, {
            "adapter": profile.key if profile else None,
            "signals": dict(state),
            "recommendations": recommendations,
        })
    except Exception as exc:  # noqa: BLE001
        return _result(OPTIMIZATION_CAPABILITY_ID, False, start, {}, str(exc)[:200])


def _auth_state(page: Any, payload: dict[str, Any]) -> dict[str, Any]:
    return dict(page.evaluate(
        """(expectedProvider) => {
          const text = (document.body?.innerText || '').replace(/\\s+/g, ' ').trim();
          const lower = text.toLowerCase();
          const inputs = Array.from(document.querySelectorAll('input')).map((node) => ({
            type: node.getAttribute('type') || 'text',
            name: node.getAttribute('name') || '',
            autocomplete: node.getAttribute('autocomplete') || '',
            label: node.getAttribute('aria-label') || node.getAttribute('placeholder') || '',
          }));
          return {
            expected_provider: expectedProvider || null,
            oauth_detected: /oauth|authorize|consent|continue with google|continue with microsoft/i.test(text),
            sso_detected: /single sign|\\bsso\\b|company account|organization/i.test(text),
            mfa_detected: /multi-factor|two-factor|authenticator|approve sign in|verification/i.test(text),
            otp_detected: /one-time|otp|verification code|security code|enter code/i.test(text) || inputs.some((input) => /one-time-code|otp/i.test(input.autocomplete + input.name + input.label)),
            captcha_detected: /captcha|recaptcha|hcaptcha/i.test(text),
            password_field_count: inputs.filter((input) => input.type === 'password').length,
            session_reuse_possible: !/sign in|login|password/i.test(lower),
          };
        }""",
        payload.get("provider") or payload.get("expected_provider") or "",
    ))


def _recommendations(signals: dict[str, Any], profile: AdapterProfile | None) -> list[str]:
    recs: list[str] = []
    if int(signals.get("contenteditable_count") or 0) > 0:
        recs.append("use_rich_text_adapter")
    if int(signals.get("table_count") or 0) > 0:
        recs.append("use_large_table_navigation")
    if int(signals.get("virtual_signals") or 0) > 0:
        recs.append("use_virtual_list_strategy")
    if int(signals.get("dashboard_signals") or 0) > 0:
        recs.append("use_visual_surface_strategy")
    if int(signals.get("navigation_count") or 0) > 0:
        recs.append("prefer_navigation_landmarks")
    if profile:
        recs.extend(f"adapter:{item}" for item in profile.optimizations)
    return _dedupe(recs)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = re.sub(r"\s+", "_", value.strip().lower())
        if key and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _result(capability_id: str, success: bool, start: float, details: dict[str, Any], error: str | None = None) -> Wave4Result:
    return Wave4Result(
        capability_id=capability_id,
        success=success,
        duration_ms=(time.perf_counter() - start) * 1000,
        details=details,
        error=error,
    )
