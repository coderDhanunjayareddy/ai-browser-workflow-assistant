"""
V7.0 Live Browser Sync Layer — BrowserEventAnalytics.

Thread-safe counters. Same pattern as V6.5 TrustAnalytics.
"""
from __future__ import annotations

import threading

from app.browser.models import BrowserEventType


class BrowserEventAnalytics:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self.events_received:          int = 0
        self.tab_created:              int = 0
        self.tab_updated:              int = 0
        self.tab_activated:            int = 0
        self.tab_closed:               int = 0
        self.url_changed:              int = 0
        self.page_loaded:              int = 0
        self.window_focused:           int = 0
        self.window_blurred:           int = 0
        self.mission_refreshes:        int = 0
        self.trust_refreshes:          int = 0
        self.recommendation_refreshes: int = 0

    def record_event(self, event_type: BrowserEventType) -> None:
        with self._lock:
            self.events_received += 1
            _MAP = {
                BrowserEventType.tab_created:    "tab_created",
                BrowserEventType.tab_updated:    "tab_updated",
                BrowserEventType.tab_activated:  "tab_activated",
                BrowserEventType.tab_closed:     "tab_closed",
                BrowserEventType.url_changed:    "url_changed",
                BrowserEventType.page_loaded:    "page_loaded",
                BrowserEventType.window_focused: "window_focused",
                BrowserEventType.window_blurred: "window_blurred",
            }
            attr = _MAP.get(event_type)
            if attr:
                setattr(self, attr, getattr(self, attr) + 1)

    def record_mission_refresh(self) -> None:
        with self._lock:
            self.mission_refreshes += 1

    def record_trust_refresh(self) -> None:
        with self._lock:
            self.trust_refreshes += 1

    def record_recommendation_refresh(self) -> None:
        with self._lock:
            self.recommendation_refreshes += 1

    def get_analytics(self) -> dict:
        with self._lock:
            return {
                "events_received":          self.events_received,
                "tab_created":              self.tab_created,
                "tab_updated":              self.tab_updated,
                "tab_activated":            self.tab_activated,
                "tab_closed":               self.tab_closed,
                "url_changed":              self.url_changed,
                "page_loaded":              self.page_loaded,
                "window_focused":           self.window_focused,
                "window_blurred":           self.window_blurred,
                "mission_refreshes":        self.mission_refreshes,
                "trust_refreshes":          self.trust_refreshes,
                "recommendation_refreshes": self.recommendation_refreshes,
            }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._reset()


# ── Module-level singleton ────────────────────────────────────────────────────

_analytics = BrowserEventAnalytics()


def record_event(event_type: BrowserEventType) -> None:
    _analytics.record_event(event_type)

def record_mission_refresh() -> None:
    _analytics.record_mission_refresh()

def record_trust_refresh() -> None:
    _analytics.record_trust_refresh()

def record_recommendation_refresh() -> None:
    _analytics.record_recommendation_refresh()

def get_analytics() -> dict:
    return _analytics.get_analytics()

def _reset_for_testing() -> None:
    _analytics._reset_for_testing()
