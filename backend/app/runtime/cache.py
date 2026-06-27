"""
V8.9 Browser Runtime Layer — ContextCache.

In-memory, per-runtime cache of the most recent ContextSnapshot.
TTL: 300 seconds. No persistence (cleared on restart, by design).

Same RLock + monotonic-clock pattern as the V7.0 BrowserEventRegistry.

Tracks cache hits / misses so RuntimeAnalytics can compute hit ratio.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from app.runtime.models import ContextSnapshot

TTL_SECONDS: float = 300.0


class ContextCache:

    def __init__(self, ttl: float = TTL_SECONDS) -> None:
        self._ttl  = ttl
        self._lock = threading.RLock()
        # runtime_id → (snapshot, inserted_monotonic)
        self._store: dict[str, tuple[ContextSnapshot, float]] = {}
        self._hits:   int = 0
        self._misses: int = 0

    # ── Write ────────────────────────────────────────────────────────────────

    def set(self, runtime_id: str, snapshot: ContextSnapshot) -> None:
        now = time.monotonic()
        with self._lock:
            self._store[runtime_id] = (snapshot, now)

    # ── Read ─────────────────────────────────────────────────────────────────

    def get(self, runtime_id: str) -> Optional[ContextSnapshot]:
        """Return the cached snapshot if fresh; counts hit/miss. Auto-evicts if stale."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(runtime_id)
            if entry is None:
                self._misses += 1
                return None
            snap, inserted = entry
            if now - inserted > self._ttl:
                del self._store[runtime_id]
                self._misses += 1
                return None
            self._hits += 1
            return snap

    def peek(self, runtime_id: str) -> Optional[ContextSnapshot]:
        """Return cached snapshot without counting a hit/miss. Respects TTL."""
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(runtime_id)
            if entry is None:
                return None
            snap, inserted = entry
            if now - inserted > self._ttl:
                return None
            return snap

    def is_fresh(self, runtime_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(runtime_id)
            if entry is None:
                return False
            return (now - entry[1]) <= self._ttl

    def age_seconds(self, runtime_id: str) -> Optional[float]:
        now = time.monotonic()
        with self._lock:
            entry = self._store.get(runtime_id)
            if entry is None:
                return None
            return round(now - entry[1], 3)

    def invalidate(self, runtime_id: str) -> bool:
        with self._lock:
            return self._store.pop(runtime_id, None) is not None

    # ── Stats ────────────────────────────────────────────────────────────────

    def count(self) -> int:
        with self._lock:
            return len(self._store)

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            ratio = round(self._hits / total, 4) if total else 0.0
            return {
                "cached_runtimes": len(self._store),
                "cache_hits":      self._hits,
                "cache_misses":    self._misses,
                "hit_ratio":       ratio,
                "ttl_seconds":     self._ttl,
            }

    def _reset_for_testing(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits   = 0
            self._misses = 0


# ── Module-level singleton ────────────────────────────────────────────────────

_cache = ContextCache()


def set(runtime_id: str, snapshot: ContextSnapshot) -> None:  _cache.set(runtime_id, snapshot)
def get(runtime_id: str) -> Optional[ContextSnapshot]:        return _cache.get(runtime_id)
def peek(runtime_id: str) -> Optional[ContextSnapshot]:       return _cache.peek(runtime_id)
def is_fresh(runtime_id: str) -> bool:                        return _cache.is_fresh(runtime_id)
def age_seconds(runtime_id: str) -> Optional[float]:          return _cache.age_seconds(runtime_id)
def invalidate(runtime_id: str) -> bool:                      return _cache.invalidate(runtime_id)
def count() -> int:                                           return _cache.count()
def stats() -> dict:                                          return _cache.stats()
def _reset_for_testing() -> None:                             _cache._reset_for_testing()
