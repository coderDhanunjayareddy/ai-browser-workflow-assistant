"""
V8.9 Browser Runtime Layer — RuntimeAnalytics.

Thread-safe counters for the runtime layer.
Same pattern as V8.8 AuthorizationAnalytics.

Tracks:
  runtime uptime          (seconds since first record / process start marker)
  cached requests         (syncs that found a cache entry to diff against)
  cache hits / misses     (mirrors ContextCache, but counted at sync time)
  context diff ratio      (running average of per-sync diff ratios)
  prefetch opportunities  (syncs that produced an actionable PrefetchHint)
  event rate              (total runtime events / total syncs)
"""
from __future__ import annotations

import threading

_lock = threading.Lock()


class _RuntimeCounters:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.started_at:           float = 0.0   # wall-clock of first sync (set externally)
        self.last_activity_at:     float = 0.0
        self.syncs:                int   = 0
        self.cached_requests:      int   = 0     # syncs with a prior cache entry
        self.cache_hits:           int   = 0
        self.cache_misses:         int   = 0
        self.total_diff_ratio:     float = 0.0
        self.diff_samples:         int   = 0
        self.prefetch_opportunities: int = 0
        self.total_events:         int   = 0


_counters = _RuntimeCounters()


def _reset_for_testing() -> None:
    with _lock:
        _counters.reset()


def record_sync(
    *,
    wall_now:     float,
    cache_hit:    bool,
    diff_ratio:   float,
    event_count:  int,
    prefetch:     bool,
) -> None:
    with _lock:
        if _counters.started_at == 0.0:
            _counters.started_at = wall_now
        _counters.last_activity_at = wall_now
        _counters.syncs += 1
        if cache_hit:
            _counters.cache_hits     += 1
            _counters.cached_requests += 1
        else:
            _counters.cache_misses += 1
        _counters.total_diff_ratio += diff_ratio
        _counters.diff_samples     += 1
        _counters.total_events     += event_count
        if prefetch:
            _counters.prefetch_opportunities += 1


def get_analytics(wall_now: float = 0.0) -> dict:
    with _lock:
        uptime = 0.0
        if _counters.started_at > 0.0:
            ref = wall_now if wall_now > 0.0 else _counters.last_activity_at
            uptime = round(max(0.0, ref - _counters.started_at), 3)
        total_cache = _counters.cache_hits + _counters.cache_misses
        hit_ratio = round(_counters.cache_hits / total_cache, 4) if total_cache else 0.0
        avg_diff  = round(_counters.total_diff_ratio / _counters.diff_samples, 4) if _counters.diff_samples else 0.0
        event_rate = round(_counters.total_events / _counters.syncs, 4) if _counters.syncs else 0.0
        return {
            "runtime_uptime_seconds": uptime,
            "syncs":                  _counters.syncs,
            "cached_requests":        _counters.cached_requests,
            "cache_hits":             _counters.cache_hits,
            "cache_misses":           _counters.cache_misses,
            "cache_hit_ratio":        hit_ratio,
            "avg_context_diff_ratio": avg_diff,
            "prefetch_opportunities": _counters.prefetch_opportunities,
            "total_events":           _counters.total_events,
            "event_rate":             event_rate,
        }
