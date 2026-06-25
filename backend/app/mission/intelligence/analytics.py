"""
V5.5 Mission Intelligence — Analytics counters.

Extends the mission analytics pattern with intelligence-specific metrics.
Uses the same in-memory counter approach as app.mission.analytics.

Counters:
  intelligence_runs         total calls to engine.run()
  cache_hits                reports served from cache
  cache_misses              reports computed fresh
  readiness_evaluations     total readiness score computations
  blocker_detections        total blocker detection runs
  total_blockers_found      cumulative blocker count
  workflow_recommendations  total workflow recommendations generated
  next_action_generations   total next-action plans generated
  total_latency_ms          cumulative latency for runs
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class _IntelCounters:
    intelligence_runs:        int   = 0
    cache_hits:               int   = 0
    cache_misses:             int   = 0
    readiness_evaluations:    int   = 0
    total_readiness_score:    float = 0.0
    blocker_detections:       int   = 0
    total_blockers_found:     int   = 0
    workflow_recommendations: int   = 0
    next_action_generations:  int   = 0
    total_latency_ms:         int   = 0


_lock     = threading.Lock()
_counters = _IntelCounters()


def record_intelligence_run(latency_ms: int) -> None:
    with _lock:
        _counters.intelligence_runs   += 1
        _counters.total_latency_ms    += latency_ms


def record_cache_hit() -> None:
    with _lock:
        _counters.cache_hits += 1


def record_cache_miss() -> None:
    with _lock:
        _counters.cache_misses += 1


def record_readiness_evaluation(score: float) -> None:
    with _lock:
        _counters.readiness_evaluations += 1
        _counters.total_readiness_score  += score


def record_blocker_detection(count: int) -> None:
    with _lock:
        _counters.blocker_detections  += 1
        _counters.total_blockers_found += count


def record_workflow_recommendation() -> None:
    with _lock:
        _counters.workflow_recommendations += 1


def record_next_action_generation() -> None:
    with _lock:
        _counters.next_action_generations += 1


def get_analytics() -> dict:
    with _lock:
        total_calls = _counters.cache_hits + _counters.cache_misses
        avg_readiness = (
            round(_counters.total_readiness_score / _counters.readiness_evaluations, 3)
            if _counters.readiness_evaluations > 0 else 0.0
        )
        avg_latency = (
            round(_counters.total_latency_ms / _counters.intelligence_runs, 1)
            if _counters.intelligence_runs > 0 else 0.0
        )
        cache_hit_rate = (
            round(_counters.cache_hits / total_calls, 3) if total_calls > 0 else 0.0
        )
        avg_blockers = (
            round(_counters.total_blockers_found / _counters.blocker_detections, 2)
            if _counters.blocker_detections > 0 else 0.0
        )
        return {
            "intelligence_runs":         _counters.intelligence_runs,
            "cache_hits":                _counters.cache_hits,
            "cache_misses":              _counters.cache_misses,
            "cache_hit_rate":            cache_hit_rate,
            "readiness_evaluations":     _counters.readiness_evaluations,
            "avg_readiness_score":       avg_readiness,
            "blocker_detections":        _counters.blocker_detections,
            "total_blockers_found":      _counters.total_blockers_found,
            "avg_blockers_per_run":      avg_blockers,
            "workflow_recommendations":  _counters.workflow_recommendations,
            "next_action_generations":   _counters.next_action_generations,
            "avg_latency_ms":            avg_latency,
        }


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _IntelCounters()
