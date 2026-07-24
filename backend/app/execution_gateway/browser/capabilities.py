"""
Phase C — Browser Capability Analysis.

Declares exactly what the Playwright Adapter V1 supports. Used by validation, the
browser-session REST endpoint, and as living documentation of scope.
"""
from __future__ import annotations

from app.capability_platform.browser_registry import certification_report
from app.feature_flags import v4_flag_snapshot

# The 11 supported action sub-types (mapped onto the 9 adapter methods).
SUPPORTED_ACTIONS: tuple[str, ...] = (
    "NAVIGATE", "CLICK", "TYPE", "WAIT",
    "EXTRACT_TEXT", "EXTRACT_HTML",
    "UPLOAD", "DOWNLOAD",
    "VALIDATE_URL", "VALIDATE_TEXT", "VALIDATE_EXISTS",
)

# Element resolution strategies in deterministic priority order (Phase C — unchanged).
RESOLUTION_PRIORITY: tuple[str, ...] = (
    "selector", "testid", "aria_label", "role", "id", "name", "css", "xpath",
)

# Phase D — Adaptive locator strategy (additive superset of RESOLUTION_PRIORITY).
# Preserves the relative order of every Phase C strategy and inserts the new ones
# (aria / label / placeholder / text) so existing resolutions are byte-identical.
EXTENDED_RESOLUTION_PRIORITY: tuple[str, ...] = (
    "selector", "testid", "aria_label", "aria", "role",
    "label", "placeholder", "text", "id", "name", "css", "xpath",
)

SUPPORTED_CONTEXT: dict[str, bool] = {
    "multiple_tabs":   True,
    "new_windows":     True,
    "page_refresh":    True,
    "popup_handling":  True,
    "iframe_basic":    True,
}

UNSUPPORTED_YET: dict[str, bool] = {
    "cross_browser":      False,
    "mobile":             False,
    "persistent_profile": False,  # V4 opt-in via V4_BROWSER_PROFILE; not default support.
    "drag_and_drop":      False,
    "cloud_browser":      False,
}

DOWNLOAD_SUPPORT: dict[str, bool] = {
    "download_detection":  True,
    "download_completion": True,
    "file_path_reporting": True,
    "cloud_upload":        False,
}

UPLOAD_SUPPORT: dict[str, bool] = {
    "input_file":     True,
    "single_file":    True,
    "multiple_files": True,
    "drag_and_drop":  False,
}


def get_capabilities() -> dict:
    return {
        "adapter":            "playwright",
        "version":            "1.0",
        "browser":            "chromium",
        "headless_default":   True,
        "supported_actions":  list(SUPPORTED_ACTIONS),
        "resolution_priority": list(RESOLUTION_PRIORITY),
        "context":            dict(SUPPORTED_CONTEXT),
        "unsupported_yet":    dict(UNSUPPORTED_YET),
        "download":           dict(DOWNLOAD_SUPPORT),
        "upload":             dict(UPLOAD_SUPPORT),
        "v4_wave_1": {
            "flags": v4_flag_snapshot(),
            "certification": certification_report(),
        },
        "v4_5_browser_intelligence": {
            "flags": {
                name: state
                for name, state in v4_flag_snapshot().items()
                if name.startswith("V45_")
            },
            "supported_adapters": [
                "generic", "google_search", "bing_search", "linkedin_jobs", "github",
                "gmail", "outlook", "notion", "jira", "confluence", "documentation",
                "generic_react_spa", "generic_dashboard", "generic_data_table",
            ],
            "planner_contract": "Planner Contract V2 preserved; V4.5 emits semantic context and explicit URLs, not new planner actions.",
        },
        "v4_6_adaptive_browser_intelligence": {
            "flags": {
                name: state
                for name, state in v4_flag_snapshot().items()
                if name.startswith("V46_")
            },
            "adaptive_capabilities": [
                "dynamic_dom_tracking",
                "intelligent_waiting",
                "browser_memory",
                "adaptive_recovery",
                "universal_adapters",
                "visual_grounding_metadata",
                "cross_validation",
                "browser_health_monitoring",
            ],
            "planner_contract": "Planner Contract V2 preserved; V4.6 adapts Browser Intelligence artifacts only.",
        },
        "ai_free":            True,   # no Vision/OCR/LLM/self-healing selectors
    }
