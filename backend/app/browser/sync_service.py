"""
V7.0 Live Browser Sync Layer — LiveSyncService.

Receives a BrowserEvent and updates the V6.0 TabRegistry.
No autonomy, no execution, no action dispatch.
Pure state synchronization: event → registry update.

Tab state transitions:
  TAB_CREATED    → register tab (RESEARCH role, OPEN state) if not exists
  TAB_UPDATED    → update url / title
  TAB_ACTIVATED  → set_active → state becomes ACTIVE
  TAB_CLOSED     → close → state becomes CLOSED
  URL_CHANGED    → update url
  PAGE_LOADED    → update url + title (page content ready)
  WINDOW_FOCUSED → no tab state change (window-level event)
  WINDOW_BLURRED → no tab state change (window-level event)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from app.browser.models import BrowserEvent, BrowserEventType
from app.tabs import registry as tab_reg
from app.tabs.models import BrowserTabRole, BrowserTabState


@dataclass
class SyncResult:
    success:         bool
    event_id:        str
    event_type:      str
    tab_updated:     bool        = False
    mission_id:      Optional[str] = None
    triggers_refresh: bool       = False
    refresh_reason:  str         = ""
    latency_ms:      int         = 0
    error:           Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "success":          self.success,
            "event_id":         self.event_id,
            "event_type":       self.event_type,
            "tab_updated":      self.tab_updated,
            "mission_id":       self.mission_id,
            "triggers_refresh": self.triggers_refresh,
            "refresh_reason":   self.refresh_reason,
            "latency_ms":       self.latency_ms,
            "error":            self.error,
        }


class LiveSyncService:

    def process_event(self, event: BrowserEvent) -> SyncResult:
        t0 = time.perf_counter()
        try:
            result = self._dispatch(event)
        except Exception as exc:
            latency_ms = int((time.perf_counter() - t0) * 1000)
            return SyncResult(
                success    = False,
                event_id   = event.event_id,
                event_type = event.event_type.value,
                error      = str(exc),
                latency_ms = latency_ms,
            )
        result.latency_ms = int((time.perf_counter() - t0) * 1000)
        return result

    def _dispatch(self, event: BrowserEvent) -> SyncResult:
        handlers = {
            BrowserEventType.tab_created:    self._handle_tab_created,
            BrowserEventType.tab_updated:    self._handle_tab_updated,
            BrowserEventType.tab_activated:  self._handle_tab_activated,
            BrowserEventType.tab_closed:     self._handle_tab_closed,
            BrowserEventType.url_changed:    self._handle_url_changed,
            BrowserEventType.page_loaded:    self._handle_page_loaded,
            BrowserEventType.window_focused: self._handle_window_event,
            BrowserEventType.window_blurred: self._handle_window_event,
        }
        handler = handlers.get(event.event_type, self._handle_unknown)
        return handler(event)

    # ── Handlers ──────────────────────────────────────────────────────────────

    def _handle_tab_created(self, event: BrowserEvent) -> SyncResult:
        existing = tab_reg.get(event.tab_id)
        updated = False
        if existing is None:
            tab_reg.register(
                tab_id     = event.tab_id,
                url        = event.url or "",
                title      = event.title or "",
                role       = BrowserTabRole.research,
                state      = BrowserTabState.open,
                mission_id = event.mission_id,
                task_id    = event.task_id,
            )
            updated = True
        else:
            if event.mission_id and not existing.mission_id:
                tab_reg.attach_mission(event.tab_id, event.mission_id)
            updated = True
        return SyncResult(
            success          = True,
            event_id         = event.event_id,
            event_type       = event.event_type.value,
            tab_updated      = updated,
            mission_id       = event.mission_id,
            triggers_refresh = True,
            refresh_reason   = "New tab registered for mission.",
        )

    def _handle_tab_updated(self, event: BrowserEvent) -> SyncResult:
        tab = tab_reg.get(event.tab_id)
        updated = False
        if tab is not None:
            tab_reg.update(
                tab_id = event.tab_id,
                url    = event.url   if event.url   else None,
                title  = event.title if event.title else None,
            )
            updated = True
        return SyncResult(
            success    = True,
            event_id   = event.event_id,
            event_type = event.event_type.value,
            tab_updated = updated,
            mission_id = event.mission_id or (tab.mission_id if tab else None),
        )

    def _handle_tab_activated(self, event: BrowserEvent) -> SyncResult:
        tab = tab_reg.set_active(event.tab_id)
        return SyncResult(
            success    = True,
            event_id   = event.event_id,
            event_type = event.event_type.value,
            tab_updated = tab is not None,
            mission_id = event.mission_id or (tab.mission_id if tab else None),
        )

    def _handle_tab_closed(self, event: BrowserEvent) -> SyncResult:
        tab = tab_reg.get(event.tab_id)
        mission_id = event.mission_id or (tab.mission_id if tab else None)
        closed = tab_reg.close(event.tab_id)
        return SyncResult(
            success          = True,
            event_id         = event.event_id,
            event_type       = event.event_type.value,
            tab_updated      = closed,
            mission_id       = mission_id,
            triggers_refresh = True,
            refresh_reason   = "Tab closed — mission tab map changed.",
        )

    def _handle_url_changed(self, event: BrowserEvent) -> SyncResult:
        tab = tab_reg.get(event.tab_id)
        updated = False
        if tab is not None and event.url:
            tab_reg.update(tab_id=event.tab_id, url=event.url)
            updated = True
        return SyncResult(
            success          = True,
            event_id         = event.event_id,
            event_type       = event.event_type.value,
            tab_updated      = updated,
            mission_id       = event.mission_id or (tab.mission_id if tab else None),
            triggers_refresh = True,
            refresh_reason   = "URL changed — mission context may be stale.",
        )

    def _handle_page_loaded(self, event: BrowserEvent) -> SyncResult:
        tab = tab_reg.get(event.tab_id)
        updated = False
        if tab is not None:
            kwargs: dict = {}
            if event.url:
                kwargs["url"]   = event.url
            if event.title:
                kwargs["title"] = event.title
            if kwargs:
                tab_reg.update(tab_id=event.tab_id, **kwargs)
                updated = True
        return SyncResult(
            success          = True,
            event_id         = event.event_id,
            event_type       = event.event_type.value,
            tab_updated      = updated,
            mission_id       = event.mission_id or (tab.mission_id if tab else None),
            triggers_refresh = True,
            refresh_reason   = "Page loaded — content ready for analysis.",
        )

    def _handle_window_event(self, event: BrowserEvent) -> SyncResult:
        return SyncResult(
            success    = True,
            event_id   = event.event_id,
            event_type = event.event_type.value,
            tab_updated = False,
            mission_id = event.mission_id,
        )

    def _handle_unknown(self, event: BrowserEvent) -> SyncResult:
        return SyncResult(
            success    = True,
            event_id   = event.event_id,
            event_type = event.event_type.value,
        )


# ── Module-level singleton ────────────────────────────────────────────────────

_service = LiveSyncService()


def process_event(event: BrowserEvent) -> SyncResult:
    return _service.process_event(event)
