"""
V5.0 Mission Layer — MissionAnalytics.

Thread-safe counters for mission-level metrics.
Kept separate from app/unified/analytics.py to avoid coupling.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _MissionCounters:
    total_missions:          int = 0
    active_missions:         int = 0
    completed_missions:      int = 0
    failed_missions:         int = 0
    abandoned_missions:      int = 0
    total_tasks_attached:    int = 0
    research_to_execution:   int = 0   # missions that had research then workflow
    total_mission_duration_ms: int = 0
    mission_count_for_avg:   int = 0


_counters = _MissionCounters()
_lock = threading.Lock()


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _MissionCounters()


# ── Record functions ──────────────────────────────────────────────────────────

def record_mission_created() -> None:
    with _lock:
        _counters.total_missions += 1
        _counters.active_missions += 1


def record_mission_completed(duration_ms: int = 0) -> None:
    with _lock:
        _counters.completed_missions += 1
        _counters.active_missions = max(0, _counters.active_missions - 1)
        if duration_ms > 0:
            _counters.total_mission_duration_ms += duration_ms
            _counters.mission_count_for_avg += 1


def record_mission_failed() -> None:
    with _lock:
        _counters.failed_missions += 1
        _counters.active_missions = max(0, _counters.active_missions - 1)


def record_mission_abandoned() -> None:
    with _lock:
        _counters.abandoned_missions += 1
        _counters.active_missions = max(0, _counters.active_missions - 1)


def record_task_attached() -> None:
    with _lock:
        _counters.total_tasks_attached += 1


def record_research_to_execution() -> None:
    with _lock:
        _counters.research_to_execution += 1


# ── Read ───────────────────────────────────────────────────────────────────────

def get_analytics() -> dict[str, Any]:
    with _lock:
        total = _counters.total_missions
        completed = _counters.completed_missions
        avg_duration = (
            _counters.total_mission_duration_ms // _counters.mission_count_for_avg
            if _counters.mission_count_for_avg > 0 else 0
        )
        avg_tasks = (
            _counters.total_tasks_attached / total
            if total > 0 else 0.0
        )
        completion_rate = completed / total if total > 0 else 0.0
        research_exec_rate = (
            _counters.research_to_execution / total if total > 0 else 0.0
        )
        return {
            "total_missions":          total,
            "active_missions":         _counters.active_missions,
            "completed_missions":      completed,
            "failed_missions":         _counters.failed_missions,
            "abandoned_missions":      _counters.abandoned_missions,
            "total_tasks_attached":    _counters.total_tasks_attached,
            "average_tasks_per_mission": round(avg_tasks, 2),
            "mission_completion_rate": round(completion_rate, 3),
            "average_mission_duration_ms": avg_duration,
            "research_to_execution_rate": round(research_exec_rate, 3),
        }
