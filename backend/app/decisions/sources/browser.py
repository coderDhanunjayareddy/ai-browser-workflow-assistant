"""
V7.5 Decision Center — Browser source adapter.

Wraps V7.0 RecommendationRefreshEngine outputs (DecisionSignal) into DecisionItems.
Does NOT re-implement recommendation logic.
"""
from __future__ import annotations

from typing import Optional

from app.decisions.models import (
    DecisionItem, DecisionType, DecisionPriority, make_decision,
)
from app.browser.models import DecisionSignalType

_SOURCE = "browser_sync"

_SIGNAL_TO_DEC_TYPE = {
    DecisionSignalType.warning:        DecisionType.trust_warning,
    DecisionSignalType.recommendation: DecisionType.recommendation,
    DecisionSignalType.info:           DecisionType.info,
}

_SIGNAL_TO_PRIORITY = {
    DecisionSignalType.warning:        DecisionPriority.high,
    DecisionSignalType.recommendation: DecisionPriority.medium,
    DecisionSignalType.info:           DecisionPriority.low,
}


def decisions_for_mission(mission_id: str) -> list[DecisionItem]:
    """
    Convert V7.0 DecisionSignals for a mission into V7.5 DecisionItems.
    Returns [] if browser layer unavailable.
    """
    items: list[DecisionItem] = []
    try:
        from app.browser.recommendation import refresh as _rec_refresh
        signals = _rec_refresh(mission_id)
        for sig in signals:
            dec_type = _SIGNAL_TO_DEC_TYPE.get(sig.signal_type, DecisionType.info)
            priority = _SIGNAL_TO_PRIORITY.get(sig.signal_type, DecisionPriority.low)
            items.append(make_decision(
                decision_type = dec_type,
                priority      = priority,
                title         = f"Browser: {sig.message[:60]}",
                description   = sig.message,
                source        = _SOURCE,
                mission_id    = mission_id,
                metadata      = {
                    "signal_id":   sig.signal_id,
                    "signal_type": sig.signal_type.value,
                    "source":      sig.source,
                },
            ))
    except Exception:
        pass
    return items
