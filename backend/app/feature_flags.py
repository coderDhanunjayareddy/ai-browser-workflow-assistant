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
    return {name: get_flag_state(name).value for name in _FLAG_SETTINGS}
