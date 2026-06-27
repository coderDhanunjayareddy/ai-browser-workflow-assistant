"""
V8.9 Browser Runtime Layer — DOMChangeDetector.

Turns the delta between two ContextSnapshots (plus session-level changes) into
lightweight RuntimeEvents. NO AI. NO network. Pure comparison.

Detection rules:
  title change                → PAGE_CHANGED
  url change                  → URL_CHANGED
  selection change            → SELECTION_CHANGED
  dom_mutation_count > 0      → DOM_UPDATED
  active_tab change           → TAB_SWITCHED      (session-level)
  active_mission change       → MISSION_SWITCHED  (session-level)
  active_task change          → TASK_SWITCHED     (session-level)
"""
from __future__ import annotations

from typing import Optional

from app.runtime.models import (
    ContextSnapshot,
    RuntimeEvent,
    RuntimeEventType,
    make_runtime_event,
)


class DOMChangeDetector:

    def detect(
        self,
        runtime_id: str,
        old: Optional[ContextSnapshot],
        new: ContextSnapshot,
        *,
        now:               float = 0.0,
        mission_id:        Optional[str] = None,
        task_id:           Optional[str] = None,
        tab_id:            Optional[str] = None,
        old_tab_id:        Optional[str] = None,
        old_mission_id:    Optional[str] = None,
        old_task_id:       Optional[str] = None,
    ) -> list[RuntimeEvent]:
        events: list[RuntimeEvent] = []

        def emit(et: RuntimeEventType, detail: dict) -> None:
            events.append(make_runtime_event(
                et, runtime_id, now=now,
                mission_id=mission_id, task_id=task_id, tab_id=tab_id,
                detail=detail,
            ))

        old_title = old.last_title if old else None
        old_url   = old.last_url   if old else None
        old_sel   = old.last_selection if old else None

        # ── Content-level (snapshot) changes ──
        if new.last_title is not None and new.last_title != old_title:
            emit(RuntimeEventType.page_changed,
                 {"from": old_title, "to": new.last_title})

        if new.last_url is not None and new.last_url != old_url:
            emit(RuntimeEventType.url_changed,
                 {"from": old_url, "to": new.last_url})

        if new.last_selection != old_sel and (new.last_selection or old_sel):
            emit(RuntimeEventType.selection_changed,
                 {"length": len(new.last_selection or "")})

        if new.dom_mutation_count and new.dom_mutation_count > 0:
            emit(RuntimeEventType.dom_updated,
                 {"mutation_count": new.dom_mutation_count})

        # ── Session-level changes ──
        if tab_id is not None and old_tab_id is not None and tab_id != old_tab_id:
            emit(RuntimeEventType.tab_switched,
                 {"from": old_tab_id, "to": tab_id})

        if mission_id is not None and old_mission_id is not None and mission_id != old_mission_id:
            emit(RuntimeEventType.mission_switched,
                 {"from": old_mission_id, "to": mission_id})

        if task_id is not None and old_task_id is not None and task_id != old_task_id:
            emit(RuntimeEventType.task_switched,
                 {"from": old_task_id, "to": task_id})

        return events


# ── Module-level singleton ────────────────────────────────────────────────────

_detector = DOMChangeDetector()


def detect(runtime_id: str, old: Optional[ContextSnapshot], new: ContextSnapshot, **kwargs) -> list[RuntimeEvent]:
    return _detector.detect(runtime_id, old, new, **kwargs)
