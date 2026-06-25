"""
V7.0 Live Browser Sync Layer — MissionRefreshEngine.

Triggered by significant browser events (TAB_CREATED, TAB_CLOSED, URL_CHANGED, PAGE_LOADED).
Recomputes mission intelligence + tab context for the affected mission.

Throttle: 2-second cooldown per mission to prevent refresh storms.
No LLM calls. No autonomy. Pure recomputation of existing deterministic engines.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional


_COOLDOWN_S: float = 2.0


@dataclass
class RefreshResult:
    mission_id:          str
    refreshed:           bool
    skipped_reason:      str          = ""
    readiness_score:     Optional[float] = None
    advisory_state:      Optional[str]   = None
    tab_count:           Optional[int]   = None
    trust_score:         Optional[float] = None
    risk_level:          Optional[str]   = None
    recommendation_count: int            = 0
    latency_ms:          int             = 0

    def to_dict(self) -> dict:
        return {
            "mission_id":           self.mission_id,
            "refreshed":            self.refreshed,
            "skipped_reason":       self.skipped_reason,
            "readiness_score":      self.readiness_score,
            "advisory_state":       self.advisory_state,
            "tab_count":            self.tab_count,
            "trust_score":          self.trust_score,
            "risk_level":           self.risk_level,
            "recommendation_count": self.recommendation_count,
            "latency_ms":           self.latency_ms,
        }


class MissionRefreshEngine:

    def __init__(self, cooldown_s: float = _COOLDOWN_S) -> None:
        self._cooldown   = cooldown_s
        self._lock       = threading.RLock()
        self._last_refresh: dict[str, float] = {}  # mission_id → monotonic time

    def refresh(self, mission_id: str, reason: str = "") -> RefreshResult:
        t0  = time.perf_counter()
        now = time.monotonic()

        # Throttle check
        with self._lock:
            last = self._last_refresh.get(mission_id, 0.0)
            if now - last < self._cooldown:
                return RefreshResult(
                    mission_id    = mission_id,
                    refreshed     = False,
                    skipped_reason = "cooldown",
                    latency_ms    = int((time.perf_counter() - t0) * 1000),
                )
            self._last_refresh[mission_id] = now

        readiness   : Optional[float] = None
        advisory    : Optional[str]   = None
        tab_count   : Optional[int]   = None
        trust_score : Optional[float] = None
        risk_level  : Optional[str]   = None
        rec_count   = 0

        # Rerun intelligence engine (force bypass cache)
        try:
            from app.mission.intelligence import engine as _intel
            report = _intel.run(mission_id, force_refresh=True)
            if report:
                readiness = report.readiness_score
                advisory  = report.advisory_state.value if report.advisory_state else None
                trust_score = report.trust_score
                risk_level  = report.risk_level
        except Exception:
            pass

        # Recompute tab context
        try:
            from app.tabs.context import build as _build_tab_ctx
            ctx = _build_tab_ctx(mission_id)
            tab_count = ctx.tab_count
        except Exception:
            pass

        # Rerun recommendation refresh
        try:
            from app.browser.recommendation import refresh as _rec_refresh
            signals = _rec_refresh(mission_id)
            rec_count = len(signals)
        except Exception:
            pass

        latency_ms = int((time.perf_counter() - t0) * 1000)
        return RefreshResult(
            mission_id           = mission_id,
            refreshed            = True,
            readiness_score      = readiness,
            advisory_state       = advisory,
            tab_count            = tab_count,
            trust_score          = trust_score,
            risk_level           = risk_level,
            recommendation_count = rec_count,
            latency_ms           = latency_ms,
        )

    def reset_cooldown(self, mission_id: str) -> None:
        with self._lock:
            self._last_refresh.pop(mission_id, None)

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._last_refresh.clear()


# ── Module-level singleton ────────────────────────────────────────────────────

_engine = MissionRefreshEngine()


def refresh(mission_id: str, reason: str = "") -> RefreshResult:
    return _engine.refresh(mission_id, reason)

def reset_cooldown(mission_id: str) -> None:
    _engine.reset_cooldown(mission_id)

def _reset_for_testing() -> None:
    _engine._reset_for_testing()
