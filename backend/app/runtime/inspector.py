"""
V8.9 Browser Runtime Layer — RuntimeInspector.

Single read-only debugging surface for a runtime session.
Aggregates: session, cache health, event summary, context freshness, prefetch
hint, mission-aware context, browser-sync linkage, and analytics.

NO execution. NO mutation. NO LLM.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from app.runtime import analytics as anal
from app.runtime import cache as ctx_cache
from app.runtime import context as runtime_context
from app.runtime import events as event_queue
from app.runtime import prefetch as prefetch_engine
from app.runtime import registry as session_reg


class RuntimeInspector:

    def inspect(self, runtime_id: str) -> dict[str, Any]:
        t0       = time.perf_counter()
        wall_now = time.time()

        session = session_reg.get(runtime_id)
        session_dict = session.to_dict() if session else None

        # Cache health
        cached_snapshot = ctx_cache.peek(runtime_id)
        cache_age       = ctx_cache.age_seconds(runtime_id)
        cache_fresh     = ctx_cache.is_fresh(runtime_id)
        cache_health = {
            "has_context":     cached_snapshot is not None,
            "is_fresh":        cache_fresh,
            "age_seconds":     cache_age,
            "context_summary": self._summarize_snapshot(cached_snapshot),
        }

        # Event summary
        event_summary = event_queue.summary(runtime_id)
        recent_events = [e.to_dict() for e in event_queue.get_for_runtime(runtime_id, limit=10)]

        # Context freshness label
        freshness = self._freshness_label(cache_age, cache_fresh)

        # Prefetch hint (recomputed from current state)
        recent = event_queue.get_for_runtime(runtime_id, limit=50)
        hint   = prefetch_engine.predict(session, recent, cached_snapshot)

        # Mission-aware context (includes authorization runtime, read-only)
        ctx = runtime_context.build(runtime_id)

        # Browser sync linkage (V7.0) — non-blocking
        browser_sync: Optional[dict] = None
        try:
            if session and session.active_mission_id:
                from app.browser import registry as browser_reg
                evs = browser_reg.events_for_mission(session.active_mission_id, limit=5)
                browser_sync = {
                    "linked_mission":      session.active_mission_id,
                    "recent_browser_events": [e.to_dict() for e in evs],
                }
        except Exception:
            pass

        latency_ms = round((time.perf_counter() - t0) * 1000, 3)

        return {
            "runtime_id":          runtime_id,
            "session":             session_dict,
            "cache_health":        cache_health,
            "context_freshness":   freshness,
            "event_summary":       event_summary,
            "recent_events":       recent_events,
            "prefetch":            hint.to_dict(),
            "runtime_context":     ctx.to_dict(),
            "authorization_runtime": {
                "execution_ready":     ctx.execution_ready,
                "authorization_state": ctx.authorization_state,
            },
            "browser_sync":        browser_sync,
            "analytics":           anal.get_analytics(wall_now=wall_now),
            "registry_stats":      session_reg.stats(),
            "cache_stats":         ctx_cache.stats(),
            "queue_stats":         event_queue.stats(),
            "latency_ms":          latency_ms,
        }

    # ── helpers ──────────────────────────────────────────────────────────────

    @staticmethod
    def _summarize_snapshot(snap) -> Optional[dict]:
        if snap is None:
            return None
        return {
            "last_url":             snap.last_url,
            "last_title":           snap.last_title,
            "read_view_chars":      len(snap.last_read_view or ""),
            "dom_summary_chars":    len(snap.last_dom_summary or ""),
            "has_selection":        bool(snap.last_selection),
            "scroll_position":      snap.last_scroll_position,
            "dom_mutation_count":   snap.dom_mutation_count,
        }

    @staticmethod
    def _freshness_label(age: Optional[float], fresh: bool) -> dict:
        if age is None:
            label = "no_context"
        elif not fresh:
            label = "stale"
        elif age < 10:
            label = "live"
        elif age < 60:
            label = "fresh"
        else:
            label = "aging"
        return {"label": label, "age_seconds": age}


# ── Module-level singleton ────────────────────────────────────────────────────

_inspector = RuntimeInspector()


def inspect(runtime_id: str) -> dict[str, Any]:
    return _inspector.inspect(runtime_id)
