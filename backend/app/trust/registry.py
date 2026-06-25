"""
V6.5 Trust Engine — TrustRegistry.

In-memory TTL cache for TrustEvaluation results.
Same RLock + monotonic TTL pattern as MissionIntelligenceRegistry (V5.5).

Cache key: (target_type.value, target_id)
TTL: 120 seconds (trust evaluations are cheap to recompute)

Invalidation:
  - invalidate(target_type, target_id) — on state change
  - invalidate_all()                   — on mission complete / abandon
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.trust.models import TrustEvaluation, TargetType

TTL_SECONDS: int = 120


class TrustRegistry:

    def __init__(self, ttl: int = TTL_SECONDS) -> None:
        self._ttl  = ttl
        self._lock = threading.RLock()
        self._cache: dict[tuple[str, str], tuple[TrustEvaluation, float]] = {}
        self._hits:   int = 0
        self._misses: int = 0

    def _key(self, target_type: TargetType, target_id: str) -> tuple[str, str]:
        return (target_type.value, target_id)

    def get(
        self, target_type: TargetType, target_id: str,
    ) -> Optional[TrustEvaluation]:
        with self._lock:
            k = self._key(target_type, target_id)
            entry = self._cache.get(k)
            if entry is None:
                self._misses += 1
                return None
            ev, stored_at = entry
            if time.monotonic() - stored_at > self._ttl:
                del self._cache[k]
                self._misses += 1
                return None
            self._hits += 1
            return ev

    def set(self, evaluation: TrustEvaluation) -> None:
        with self._lock:
            k = self._key(evaluation.target_type, evaluation.target_id)
            self._cache[k] = (evaluation, time.monotonic())

    def invalidate(self, target_type: TargetType, target_id: str) -> bool:
        with self._lock:
            k = self._key(target_type, target_id)
            return self._cache.pop(k, None) is not None

    def invalidate_all(self) -> int:
        with self._lock:
            n = len(self._cache)
            self._cache.clear()
            return n

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
_registry = TrustRegistry()


def get(target_type: TargetType, target_id: str) -> Optional[TrustEvaluation]:
    return _registry.get(target_type, target_id)


def set_evaluation(evaluation: TrustEvaluation) -> None:
    _registry.set(evaluation)


def invalidate(target_type: TargetType, target_id: str) -> bool:
    return _registry.invalidate(target_type, target_id)


def invalidate_all() -> int:
    return _registry.invalidate_all()


def stats() -> dict:
    return _registry.stats()


def _reset_for_testing() -> None:
    _registry._reset_for_testing()
