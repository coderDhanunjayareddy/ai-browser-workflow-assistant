"""
V8.9 Browser Runtime Layer — PredictivePrefetch.

PURE HEURISTIC. No LLM. No network. Metadata only.

Given the current session, recent runtime events, and the cached context, suggest
which *kind* of context the assistant should prepare next. This produces a
PrefetchHint only — it never fetches, never crawls, never calls a model.

Heuristics (first match wins, evaluated in order):
  1. COMPARE   — user is moving across multiple pages/tabs (>=2 URL/TAB switches)
                 or comparison-shaped titles ("vs", "compare", "review").
  2. QA        — user is making repeated selections (>=3 SELECTION_CHANGED events)
                 — a question/answer interaction pattern.
  3. SUMMARIZE — user is on a single long article (read_view length above threshold)
                 with little navigation.
  4. NONE      — nothing actionable.
"""
from __future__ import annotations

from typing import Optional

from app.runtime.models import (
    ContextSnapshot,
    PrefetchHint,
    PrefetchType,
    RuntimeEvent,
    RuntimeEventType,
    RuntimeSession,
)

LONG_ARTICLE_CHARS:   int = 2500
MIN_SELECTIONS_FOR_QA: int = 3
MIN_SWITCHES_COMPARE:  int = 2
COMPARE_KEYWORDS = ("vs", "versus", "compare", "comparison", "review", "best ")


class PredictivePrefetch:

    def predict(
        self,
        session: Optional[RuntimeSession],
        events:  list[RuntimeEvent],
        context: Optional[ContextSnapshot],
    ) -> PrefetchHint:
        # Count event signals
        selection_changes = sum(1 for e in events if e.event_type == RuntimeEventType.selection_changed)
        url_changes       = sum(1 for e in events if e.event_type == RuntimeEventType.url_changed)
        tab_switches      = sum(1 for e in events if e.event_type == RuntimeEventType.tab_switched)
        page_changes      = sum(1 for e in events if e.event_type == RuntimeEventType.page_changed)
        nav_signal        = url_changes + tab_switches

        title    = (context.last_title or "") if context else ""
        readview = (context.last_read_view or "") if context else ""
        read_len = len(readview)

        signals = {
            "selection_changes": selection_changes,
            "url_changes":       url_changes,
            "tab_switches":      tab_switches,
            "page_changes":      page_changes,
            "read_view_chars":   read_len,
        }

        title_lower = title.lower()
        title_is_compare = any(k in title_lower for k in COMPARE_KEYWORDS)

        # 1. COMPARE
        if nav_signal >= MIN_SWITCHES_COMPARE or title_is_compare:
            conf = 0.8 if (nav_signal >= MIN_SWITCHES_COMPARE and title_is_compare) else 0.6
            return PrefetchHint(
                prefetch_type=PrefetchType.compare,
                reason="multiple-page navigation / comparison-shaped title",
                confidence=conf,
                signals=signals,
            )

        # 2. QA
        if selection_changes >= MIN_SELECTIONS_FOR_QA:
            return PrefetchHint(
                prefetch_type=PrefetchType.qa,
                reason="repeated selections indicate Q&A interaction",
                confidence=0.7,
                signals=signals,
            )

        # 3. SUMMARIZE
        if read_len >= LONG_ARTICLE_CHARS and nav_signal == 0:
            return PrefetchHint(
                prefetch_type=PrefetchType.summarize,
                reason="long single-page article with little navigation",
                confidence=0.65,
                signals=signals,
            )

        # 4. NONE
        return PrefetchHint(
            prefetch_type=PrefetchType.none,
            reason="no actionable prefetch pattern",
            confidence=0.0,
            signals=signals,
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_prefetch = PredictivePrefetch()


def predict(
    session: Optional[RuntimeSession],
    events:  list[RuntimeEvent],
    context: Optional[ContextSnapshot],
) -> PrefetchHint:
    return _prefetch.predict(session, events, context)
