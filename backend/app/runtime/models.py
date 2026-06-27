"""
V8.9 Browser Runtime Layer — Domain Models.

The Browser Runtime is an OBSERVE / SYNC / PREDICT / CACHE layer.
It does NOT execute, dispatch workflows, automate the browser, or call an LLM.

Models:
  RuntimeState      : lifecycle state of a runtime session
  RuntimeEventType  : 7 lightweight runtime events (no AI)
  PrefetchType      : heuristic prefetch category (no LLM)
  RuntimeSession    : one browser-window runtime session
  ContextSnapshot   : cached page context (6 fields, TTL-bound)
  ContextDiff       : added / removed / modified between two snapshots
  RuntimeEvent      : a single detected runtime event
  PrefetchHint      : heuristic, metadata-only prefetch suggestion
  RuntimeContext    : mission awareness (mission/task/approval/authorization)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


# ── Runtime state ─────────────────────────────────────────────────────────────

class RuntimeState(str, Enum):
    idle    = "IDLE"       # session created, no sync yet
    active  = "ACTIVE"     # recently synced, context fresh
    syncing = "SYNCING"    # mid-sync (transient)
    stale   = "STALE"      # context older than TTL


# ── Runtime event types ───────────────────────────────────────────────────────

class RuntimeEventType(str, Enum):
    page_changed      = "PAGE_CHANGED"
    url_changed       = "URL_CHANGED"
    selection_changed = "SELECTION_CHANGED"
    dom_updated       = "DOM_UPDATED"
    tab_switched      = "TAB_SWITCHED"
    mission_switched  = "MISSION_SWITCHED"
    task_switched     = "TASK_SWITCHED"


ALL_RUNTIME_EVENT_TYPES: tuple[RuntimeEventType, ...] = tuple(RuntimeEventType)


# ── Prefetch type (heuristic, no LLM) ─────────────────────────────────────────

class PrefetchType(str, Enum):
    none      = "NONE"
    summarize = "SUMMARIZE"
    qa        = "QA"
    compare   = "COMPARE"


# ── RuntimeSession ────────────────────────────────────────────────────────────

@dataclass
class RuntimeSession:
    runtime_id:        str
    browser_window_id: Optional[str] = None
    active_tab_id:     Optional[str] = None
    active_mission_id: Optional[str] = None
    active_task_id:    Optional[str] = None
    runtime_state:     RuntimeState  = RuntimeState.idle
    created_at:        float         = 0.0
    updated_at:        float         = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id":        self.runtime_id,
            "browser_window_id": self.browser_window_id,
            "active_tab_id":     self.active_tab_id,
            "active_mission_id": self.active_mission_id,
            "active_task_id":    self.active_task_id,
            "runtime_state":     self.runtime_state.value,
            "created_at":        self.created_at,
            "updated_at":        self.updated_at,
        }


def make_session(
    *,
    runtime_id:        Optional[str] = None,
    browser_window_id: Optional[str] = None,
    active_tab_id:     Optional[str] = None,
    active_mission_id: Optional[str] = None,
    active_task_id:    Optional[str] = None,
    now:               float         = 0.0,
) -> RuntimeSession:
    rid = runtime_id or f"rt-{str(uuid.uuid4())[:12]}"
    return RuntimeSession(
        runtime_id        = rid,
        browser_window_id = browser_window_id,
        active_tab_id     = active_tab_id,
        active_mission_id = active_mission_id,
        active_task_id    = active_task_id,
        runtime_state     = RuntimeState.idle,
        created_at        = now,
        updated_at        = now,
    )


# ── ContextSnapshot — the cached page context ─────────────────────────────────

# The 6 cached context fields (order matters for diff ratio denominator).
CONTEXT_FIELDS: tuple[str, ...] = (
    "last_read_view",
    "last_dom_summary",
    "last_selection",
    "last_url",
    "last_title",
    "last_scroll_position",
)


@dataclass
class ContextSnapshot:
    last_read_view:       Optional[str] = None
    last_dom_summary:     Optional[str] = None
    last_selection:       Optional[str] = None
    last_url:             Optional[str] = None
    last_title:           Optional[str] = None
    last_scroll_position: Optional[int] = None
    cached_at:            float         = 0.0
    dom_mutation_count:   int           = 0

    def field_value(self, name: str) -> Any:
        return getattr(self, name, None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_read_view":       self.last_read_view,
            "last_dom_summary":     self.last_dom_summary,
            "last_selection":       self.last_selection,
            "last_url":             self.last_url,
            "last_title":           self.last_title,
            "last_scroll_position": self.last_scroll_position,
            "cached_at":            self.cached_at,
            "dom_mutation_count":   self.dom_mutation_count,
        }


# ── ContextDiff — incremental sync payload ────────────────────────────────────

@dataclass
class ContextDiff:
    added:    dict[str, Any] = field(default_factory=dict)   # field → new value (was None)
    removed:  dict[str, Any] = field(default_factory=dict)   # field → old value (now None)
    modified: dict[str, Any] = field(default_factory=dict)   # field → new value (changed)

    @property
    def changed_field_count(self) -> int:
        return len(self.added) + len(self.removed) + len(self.modified)

    @property
    def has_changes(self) -> bool:
        return self.changed_field_count > 0

    @property
    def diff_ratio(self) -> float:
        total = len(CONTEXT_FIELDS)
        if total == 0:
            return 0.0
        return round(self.changed_field_count / total, 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "added":               self.added,
            "removed":             self.removed,
            "modified":            self.modified,
            "changed_field_count": self.changed_field_count,
            "has_changes":         self.has_changes,
            "diff_ratio":          self.diff_ratio,
        }


# ── RuntimeEvent ──────────────────────────────────────────────────────────────

@dataclass
class RuntimeEvent:
    event_id:   str
    event_type: RuntimeEventType
    runtime_id: str
    timestamp:  float
    mission_id: Optional[str]      = None
    task_id:    Optional[str]      = None
    tab_id:     Optional[str]      = None
    detail:     dict[str, Any]     = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id":   self.event_id,
            "event_type": self.event_type.value,
            "runtime_id": self.runtime_id,
            "timestamp":  self.timestamp,
            "mission_id": self.mission_id,
            "task_id":    self.task_id,
            "tab_id":     self.tab_id,
            "detail":     self.detail,
        }


def make_runtime_event(
    event_type: RuntimeEventType,
    runtime_id: str,
    *,
    now:        float = 0.0,
    mission_id: Optional[str] = None,
    task_id:    Optional[str] = None,
    tab_id:     Optional[str] = None,
    detail:     Optional[dict] = None,
) -> RuntimeEvent:
    return RuntimeEvent(
        event_id   = f"re-{str(uuid.uuid4())[:12]}",
        event_type = event_type,
        runtime_id = runtime_id,
        timestamp  = now,
        mission_id = mission_id,
        task_id    = task_id,
        tab_id     = tab_id,
        detail     = detail or {},
    )


# ── PrefetchHint — heuristic, metadata-only ───────────────────────────────────

@dataclass
class PrefetchHint:
    prefetch_type: PrefetchType
    reason:        str
    confidence:    float          = 0.0   # 0.0–1.0 heuristic confidence
    signals:       dict[str, Any] = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        return self.prefetch_type != PrefetchType.none

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefetch_type": self.prefetch_type.value,
            "reason":        self.reason,
            "confidence":    self.confidence,
            "is_actionable": self.is_actionable,
            "signals":       self.signals,
        }


# ── RuntimeContext — mission awareness ────────────────────────────────────────

@dataclass
class RuntimeContext:
    runtime_id:          str
    active_mission_id:   Optional[str] = None
    active_task_id:      Optional[str] = None
    mission_state:       Optional[str] = None
    approval_state:      Optional[dict] = None     # approval summary (read-only)
    authorization_state: Optional[dict] = None     # authorization summary (read-only)
    execution_ready:     bool          = False     # UI metadata only — never gates anything
    evaluated_at:        float         = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "runtime_id":          self.runtime_id,
            "active_mission_id":   self.active_mission_id,
            "active_task_id":      self.active_task_id,
            "mission_state":       self.mission_state,
            "approval_state":      self.approval_state,
            "authorization_state": self.authorization_state,
            "execution_ready":     self.execution_ready,
            "evaluated_at":        self.evaluated_at,
        }
