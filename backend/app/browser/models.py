"""
V7.0 Live Browser Sync Layer — Domain Models.

BrowserEvent         : single browser lifecycle event from the extension
BrowserEventType     : 8 event types (TAB_CREATED … WINDOW_BLURRED)
DecisionSignal       : WARNING / RECOMMENDATION / INFO advisory output
DecisionSignalType   : signal severity enum
BrowserEventPayload  : Chrome Extension wire contract (documented, not wired)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# ── Event types ───────────────────────────────────────────────────────────────

class BrowserEventType(str, Enum):
    tab_created    = "TAB_CREATED"
    tab_updated    = "TAB_UPDATED"
    tab_activated  = "TAB_ACTIVATED"
    tab_closed     = "TAB_CLOSED"
    url_changed    = "URL_CHANGED"
    page_loaded    = "PAGE_LOADED"
    window_focused = "WINDOW_FOCUSED"
    window_blurred = "WINDOW_BLURRED"


# Events that trigger downstream refreshes (mission / trust / recommendation)
REFRESH_TRIGGER_TYPES: frozenset[BrowserEventType] = frozenset({
    BrowserEventType.tab_created,
    BrowserEventType.tab_closed,
    BrowserEventType.url_changed,
    BrowserEventType.page_loaded,
})


# ── BrowserEvent ──────────────────────────────────────────────────────────────

@dataclass
class BrowserEvent:
    event_id:   str
    event_type: BrowserEventType
    tab_id:     str
    timestamp:  datetime
    url:        Optional[str]       = None
    title:      Optional[str]       = None
    mission_id: Optional[str]       = None
    task_id:    Optional[str]       = None
    metadata:   dict[str, Any]      = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id":   self.event_id,
            "event_type": self.event_type.value,
            "tab_id":     self.tab_id,
            "timestamp":  self.timestamp.isoformat(),
            "url":        self.url,
            "title":      self.title,
            "mission_id": self.mission_id,
            "task_id":    self.task_id,
            "metadata":   self.metadata,
        }

    @property
    def triggers_refresh(self) -> bool:
        return self.event_type in REFRESH_TRIGGER_TYPES


def make_event(
    event_type: BrowserEventType,
    tab_id:     str,
    *,
    url:        Optional[str] = None,
    title:      Optional[str] = None,
    mission_id: Optional[str] = None,
    task_id:    Optional[str] = None,
    metadata:   Optional[dict] = None,
) -> BrowserEvent:
    return BrowserEvent(
        event_id   = str(uuid.uuid4())[:12],
        event_type = event_type,
        tab_id     = tab_id,
        timestamp  = datetime.utcnow(),
        url        = url,
        title      = title,
        mission_id = mission_id,
        task_id    = task_id,
        metadata   = metadata or {},
    )


# ── DecisionSignal ────────────────────────────────────────────────────────────

class DecisionSignalType(str, Enum):
    warning        = "WARNING"
    recommendation = "RECOMMENDATION"
    info           = "INFO"


@dataclass
class DecisionSignal:
    signal_id:   str
    signal_type: DecisionSignalType
    target_id:   str
    message:     str
    source:      str           # component that generated it
    created_at:  datetime
    metadata:    dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id":   self.signal_id,
            "signal_type": self.signal_type.value,
            "target_id":   self.target_id,
            "message":     self.message,
            "source":      self.source,
            "created_at":  self.created_at.isoformat(),
            "metadata":    self.metadata,
        }


def make_signal(
    signal_type: DecisionSignalType,
    target_id:   str,
    message:     str,
    source:      str,
    metadata:    Optional[dict] = None,
) -> DecisionSignal:
    return DecisionSignal(
        signal_id   = str(uuid.uuid4())[:12],
        signal_type = signal_type,
        target_id   = target_id,
        message     = message,
        source      = source,
        created_at  = datetime.utcnow(),
        metadata    = metadata or {},
    )


# ── BrowserEventPayload — Chrome Extension wire contract ──────────────────────
#
# This is the shape of the JSON body the extension posts to /browser/events.
# Chrome API listeners are NOT wired here; this is the backend contract only.
# When V7.5 wires live listeners, they will post payloads conforming to this.

@dataclass
class BrowserEventPayload:
    """
    Extension → Backend contract.

    The Chrome extension posts a JSON body with these fields.
    All optional fields default to None when not relevant for the event type.

    Mapping to BrowserEvent:
      event_type → BrowserEventType enum value string
      tab_id     → BrowserEvent.tab_id
      url        → BrowserEvent.url
      title      → BrowserEvent.title
      timestamp  → parsed to datetime; falls back to server time
      mission_id → BrowserEvent.mission_id (set by extension from side panel state)
      task_id    → BrowserEvent.task_id
    """
    event_type: str
    tab_id:     str
    url:        Optional[str] = None
    title:      Optional[str] = None
    timestamp:  Optional[str] = None  # ISO 8601
    mission_id: Optional[str] = None
    task_id:    Optional[str] = None
    metadata:   dict[str, Any] = field(default_factory=dict)

    def to_browser_event(self) -> BrowserEvent:
        try:
            et = BrowserEventType(self.event_type)
        except ValueError:
            et = BrowserEventType.tab_updated

        ts: datetime
        if self.timestamp:
            try:
                ts = datetime.fromisoformat(self.timestamp.replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                ts = datetime.utcnow()
        else:
            ts = datetime.utcnow()

        return BrowserEvent(
            event_id   = str(uuid.uuid4())[:12],
            event_type = et,
            tab_id     = self.tab_id,
            timestamp  = ts,
            url        = self.url,
            title      = self.title,
            mission_id = self.mission_id,
            task_id    = self.task_id,
            metadata   = self.metadata,
        )
