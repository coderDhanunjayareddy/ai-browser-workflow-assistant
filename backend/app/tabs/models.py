"""
V6.0 Multi-Tab Coordination Layer — Domain Models.

Pure Python dataclasses + enums. No Pydantic, no DB.
Pydantic serialization lives in app/schemas/tabs.py.

BrowserTab is the mission-level tab object — it is mission-aware and
globally registered, unlike the task-embedded TaskTab (V4.5).

Safety: Tab Layer is OBSERVATION + COORDINATION only.
  - No auto-switching.
  - No background automation.
  - No hidden execution.
  - Human remains in control.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── State machine ─────────────────────────────────────────────────────────────

class BrowserTabState(str, Enum):
    """Lifecycle state of a browser tab known to the platform."""
    open       = "OPEN"        # registered, not yet active
    active     = "ACTIVE"      # currently focused by user
    background = "BACKGROUND"  # opened but not in focus
    closed     = "CLOSED"      # closed by user or platform


TERMINAL_TAB_STATES: set[BrowserTabState] = {BrowserTabState.closed}

ACTIVE_TAB_STATES: set[BrowserTabState] = {
    BrowserTabState.open,
    BrowserTabState.active,
    BrowserTabState.background,
}


# ── Role taxonomy ─────────────────────────────────────────────────────────────

class BrowserTabRole(str, Enum):
    """
    Purpose a browser tab serves within a Mission.

    PRIMARY    — the main decision or result tab
    RESEARCH   — gathering information (equivalent to V4.5 TabRole.research)
    COMPARISON — side-by-side option evaluation
    WORKFLOW   — workflow execution in progress
    REFERENCE  — supporting context (documentation, price history, etc.)
    """
    primary    = "PRIMARY"
    research   = "RESEARCH"
    comparison = "COMPARISON"
    workflow   = "WORKFLOW"
    reference  = "REFERENCE"


# ── Core domain object ────────────────────────────────────────────────────────

@dataclass
class BrowserTab:
    """
    A browser tab known to the Multi-Tab Coordination Layer.

    Linked (optionally) to a Mission and a UnifiedTask by ID only —
    never holds a reference to the object itself.
    """
    tab_id:     str
    url:        str
    title:      str
    role:       BrowserTabRole
    state:      BrowserTabState = BrowserTabState.open
    mission_id: Optional[str]   = None
    task_id:    Optional[str]   = None
    created_at: datetime        = field(default_factory=datetime.utcnow)
    updated_at: datetime        = field(default_factory=datetime.utcnow)

    def touch(self) -> None:
        self.updated_at = datetime.utcnow()

    @property
    def is_active(self) -> bool:
        return self.state in ACTIVE_TAB_STATES

    @property
    def is_closed(self) -> bool:
        return self.state == BrowserTabState.closed

    def to_summary(self) -> dict:
        return {
            "tab_id":     self.tab_id,
            "url":        self.url,
            "title":      self.title,
            "role":       self.role.value,
            "state":      self.state.value,
            "mission_id": self.mission_id,
            "task_id":    self.task_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


def create_tab(
    url:        str,
    title:      str,
    role:       BrowserTabRole,
    state:      BrowserTabState = BrowserTabState.open,
    mission_id: Optional[str]   = None,
    task_id:    Optional[str]   = None,
    tab_id:     Optional[str]   = None,
) -> BrowserTab:
    """Factory: create a new BrowserTab with a generated ID."""
    return BrowserTab(
        tab_id     = tab_id or str(uuid.uuid4())[:12],
        url        = url,
        title      = title,
        role       = role,
        state      = state,
        mission_id = mission_id,
        task_id    = task_id,
    )


# ── Extension contract for V6.5 Chrome sync ───────────────────────────────────

@dataclass
class TabSyncPayload:
    """
    V6.5 Extension Integration Contract.

    This payload shape defines the data that the Chrome Extension service worker
    will POST to /tabs/sync when V6.5 is implemented.

    DO NOT implement Chrome API changes yet.
    This dataclass documents the agreed shape so V6.5 can begin without redesign.
    """
    tab_id:     str
    url:        str
    title:      str
    active:     bool               = False
    mission_id: Optional[str]      = None
    task_id:    Optional[str]      = None
    timestamp:  datetime           = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "tab_id":     self.tab_id,
            "url":        self.url,
            "title":      self.title,
            "active":     self.active,
            "mission_id": self.mission_id,
            "task_id":    self.task_id,
            "timestamp":  self.timestamp.isoformat(),
        }
