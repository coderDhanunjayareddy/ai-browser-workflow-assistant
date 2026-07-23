from __future__ import annotations

from enum import Enum

from app.core.config import settings


class FeatureFlagState(str, Enum):
    OFF = "off"
    SHADOW = "shadow"
    ACTIVE = "active"


_FLAG_SETTINGS: dict[str, str] = {
    "V3_RUN_LEDGER": "v3_run_ledger",
    "V3_TRACE_PARITY": "v3_trace_parity",
    "V3_CAPABILITY_PLATFORM": "v3_capability_platform",
    "V3_SCHEDULER": "v3_scheduler",
    "V3_COST_CONTROLLER": "v3_cost_controller",
    "V3_SEMANTIC_GRAPH": "v3_semantic_graph",
    "V3_CONTEXT_PACKET": "v3_context_packet",
    "V3_INTENT_GROUNDING": "v3_intent_grounding",
    "V3_MISSION_INTELLIGENCE": "v3_mission_intelligence",
    "V3_VALIDATION": "v3_validation",
    "V3_VALIDATION_OBJECT": "v3_validation",
    "V3_GOVERNANCE": "v3_governance",
    "V3_POLICY_ENGINE": "v3_governance",
    "V3_LEARNING": "v3_learning",
    "V3_EVALUATION": "v3_learning",
    "V4_SMART_WAITS": "v4_smart_waits",
    "V4_LOCATOR_RESILIENCE": "v4_locator_resilience",
    "V4_ACTION_VERIFICATION": "v4_action_verification",
    "V4_NATIVE_FORMS": "v4_native_forms",
    "V4_CUSTOM_SELECTS": "v4_custom_selects",
    "V4_DATE_TIME_PICKERS": "v4_date_time_pickers",
    "V4_OVERLAY_HANDLING": "v4_overlay_handling",
    "V4_TOAST_DETECTION": "v4_toast_detection",
    "V4_MULTI_TAB_HARDENING": "v4_multi_tab_hardening",
    "V4_HISTORY_CONTROL": "v4_history_control",
    "V4_UPLOAD_ENGINE": "v4_upload_engine",
    "V4_DOWNLOAD_LIFECYCLE": "v4_download_lifecycle",
    "V4_AUTH_HANDOFF": "v4_auth_handoff",
    "V4_BROWSER_PROFILE": "v4_browser_profile",
    "V4_BROWSER_OBSERVABILITY": "v4_browser_observability",
    "V4_BROWSER_REPLAY": "v4_browser_replay",
    "V4_CAPABILITY_CERTIFICATION": "v4_capability_certification",
    "V4_RICH_TEXT_EDITING": "v4_rich_text_editing",
    "V4_MONACO_EDITOR": "v4_monaco_editor",
    "V4_CODEMIRROR_EDITOR": "v4_codemirror_editor",
    "V4_DRAG_DROP": "v4_drag_drop",
    "V4_VIRTUAL_LISTS": "v4_virtual_lists",
    "V4_SHADOW_DOM": "v4_shadow_dom",
    "V4_INFINITE_SCROLL": "v4_infinite_scroll",
    "V4_ADVANCED_KEYBOARD": "v4_advanced_keyboard",
    "V4_CLIPBOARD": "v4_clipboard",
    "V4_CANVAS": "v4_canvas",
    "V4_SVG_INTERACTION": "v4_svg_interaction",
    "V4_PDF_VIEWER": "v4_pdf_viewer",
    "V4_CHARTS": "v4_charts",
    "V4_MAPS": "v4_maps",
    "V4_MEDIA_CONTROLS": "v4_media_controls",
    "V4_FILE_PREVIEW": "v4_file_preview",
    "V4_VISUAL_REGIONS": "v4_visual_regions",
}


def get_flag_state(flag_name: str) -> FeatureFlagState:
    attr = _FLAG_SETTINGS.get(flag_name)
    raw = getattr(settings, attr, "off") if attr else "off"
    try:
        return FeatureFlagState(str(raw).strip().lower())
    except ValueError:
        return FeatureFlagState.OFF


def is_shadow_or_active(flag_name: str) -> bool:
    return get_flag_state(flag_name) in {
        FeatureFlagState.SHADOW,
        FeatureFlagState.ACTIVE,
    }


def is_active(flag_name: str) -> bool:
    return get_flag_state(flag_name) == FeatureFlagState.ACTIVE


def v3_flag_snapshot() -> dict[str, str]:
    return {
        name: get_flag_state(name).value
        for name in _FLAG_SETTINGS
        if name.startswith("V3_")
    }


def v4_flag_snapshot() -> dict[str, str]:
    return {
        name: get_flag_state(name).value
        for name in _FLAG_SETTINGS
        if name.startswith("V4_")
    }
