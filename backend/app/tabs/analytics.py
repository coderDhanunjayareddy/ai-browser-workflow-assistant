"""
V6.0 Multi-Tab Coordination Layer — TabAnalytics.

Thread-safe counters for tab-level metrics.
Follows the same pattern as app/mission/analytics.py.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any


@dataclass
class _TabCounters:
    tabs_created:       int = 0
    tabs_closed:        int = 0
    tabs_restored:      int = 0
    tab_snapshots:      int = 0
    mission_tab_links:  int = 0
    task_tab_links:     int = 0
    context_builds:     int = 0
    intelligence_runs:  int = 0
    total_latency_ms:   int = 0
    run_count:          int = 0


_counters = _TabCounters()
_lock = threading.Lock()


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _TabCounters()


# ── Record functions ──────────────────────────────────────────────────────────

def record_tab_created() -> None:
    with _lock:
        _counters.tabs_created += 1


def record_tab_closed() -> None:
    with _lock:
        _counters.tabs_closed += 1


def record_tab_restored() -> None:
    with _lock:
        _counters.tabs_restored += 1


def record_snapshot() -> None:
    with _lock:
        _counters.tab_snapshots += 1


def record_mission_link() -> None:
    with _lock:
        _counters.mission_tab_links += 1


def record_task_link() -> None:
    with _lock:
        _counters.task_tab_links += 1


def record_context_build(latency_ms: int = 0) -> None:
    with _lock:
        _counters.context_builds += 1
        _counters.total_latency_ms += latency_ms
        _counters.run_count += 1


def record_intelligence_run() -> None:
    with _lock:
        _counters.intelligence_runs += 1


# ── Read ──────────────────────────────────────────────────────────────────────

def get_analytics() -> dict[str, Any]:
    with _lock:
        avg_latency = (
            _counters.total_latency_ms // _counters.run_count
            if _counters.run_count > 0 else 0
        )
        active_tabs = _counters.tabs_created - _counters.tabs_closed
        return {
            "tabs_created":      _counters.tabs_created,
            "tabs_closed":       _counters.tabs_closed,
            "tabs_restored":     _counters.tabs_restored,
            "active_tabs":       max(0, active_tabs),
            "tab_snapshots":     _counters.tab_snapshots,
            "mission_tab_links": _counters.mission_tab_links,
            "task_tab_links":    _counters.task_tab_links,
            "context_builds":    _counters.context_builds,
            "intelligence_runs": _counters.intelligence_runs,
            "avg_latency_ms":    avg_latency,
        }
