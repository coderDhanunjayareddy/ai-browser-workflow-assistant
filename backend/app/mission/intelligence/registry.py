"""
V5.5 Mission Intelligence — MissionIntelligenceRegistry.

In-memory TTL cache for MissionIntelligenceReport.

Design:
  - Thread-safe dict keyed by mission_id
  - TTL: 60 seconds (configurable via TTL_SECONDS)
  - Auto-invalidation: call invalidate(mission_id) when task state changes
  - Cache stats tracked for analytics (hits, misses)

Rationale: Intelligence computation is cheap (<10ms) but called on every
  UI render of mission detail. Cache prevents re-computation on every
  API request when nothing has changed.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.mission.intelligence.models import MissionIntelligenceReport

TTL_SECONDS: int = 60


class MissionIntelligenceRegistry:

    def __init__(self, ttl: int = TTL_SECONDS) -> None:
        self._ttl = ttl
        self._lock = threading.RLock()
        self._cache: dict[str, tuple[MissionIntelligenceReport, float]] = {}
        self._hits:   int = 0
        self._misses: int = 0

    def get(self, mission_id: str) -> Optional[MissionIntelligenceReport]:
        with self._lock:
            entry = self._cache.get(mission_id)
            if entry is None:
                self._misses += 1
                return None
            report, stored_at = entry
            if time.monotonic() - stored_at > self._ttl:
                del self._cache[mission_id]
                self._misses += 1
                return None
            self._hits += 1
            return report

    def set(self, mission_id: str, report: MissionIntelligenceReport) -> None:
        with self._lock:
            self._cache[mission_id] = (report, time.monotonic())

    def invalidate(self, mission_id: str) -> bool:
        with self._lock:
            return self._cache.pop(mission_id, None) is not None

    def invalidate_all(self) -> int:
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "cache_size":   len(self._cache),
                "cache_hits":   self._hits,
                "cache_misses": self._misses,
                "hit_rate":     round(self._hits / total, 3) if total > 0 else 0.0,
            }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits   = 0
            self._misses = 0


# Module-level singleton
_registry = MissionIntelligenceRegistry()


def get(mission_id: str) -> Optional[MissionIntelligenceReport]:
    return _registry.get(mission_id)


def set_report(mission_id: str, report: MissionIntelligenceReport) -> None:
    _registry.set(mission_id, report)


def invalidate(mission_id: str) -> bool:
    return _registry.invalidate(mission_id)


def invalidate_all() -> int:
    return _registry.invalidate_all()


def stats() -> dict:
    return _registry.stats()


def _reset_for_testing() -> None:
    _registry._reset_for_testing()
