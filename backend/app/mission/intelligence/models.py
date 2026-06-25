"""
V5.5 Mission Intelligence Layer — Domain Models.

All models are pure Python dataclasses — no Pydantic, no DB.
Pydantic schemas for REST serialization live in app/schemas/mission_intelligence.py.

Advisory note: MissionIntelligenceReport is ADVISORY ONLY.
  - readiness_score tells you HOW READY the mission is
  - recommended_action tells you WHAT should happen next
  - advisory_state tells you WHAT STATE is advised
None of these mutate Mission state. Human remains in control.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ── Advisory state (never mutates actual MissionState) ────────────────────────

class MissionAdvisoryState(str, Enum):
    """What state Mission Intelligence recommends the mission be treated as."""
    active    = "ACTIVE"
    paused    = "PAUSED"
    blocked   = "BLOCKED"
    ready     = "READY"
    completed = "COMPLETED"


# ── Blocker severity ──────────────────────────────────────────────────────────

class BlockerSeverity(str, Enum):
    critical = "CRITICAL"   # blocks execution entirely
    warning  = "WARNING"    # degrades confidence but doesn't block
    info     = "INFO"       # informational only


# ── Information gap categories ────────────────────────────────────────────────

class GapCategory(str, Enum):
    temporal     = "TEMPORAL"     # date/time related
    financial    = "FINANCIAL"    # price/budget/payment
    identity     = "IDENTITY"     # email/name/account
    geographic   = "GEOGRAPHIC"   # origin/destination/location
    demographic  = "DEMOGRAPHIC"  # traveler count, headcount
    product      = "PRODUCT"      # product name/model/spec
    contact      = "CONTACT"      # recipient/phone/address
    credential   = "CREDENTIAL"   # login/password (advisory only)
    unknown      = "UNKNOWN"


# ── Core data classes ──────────────────────────────────────────────────────────

@dataclass
class MissionBlocker:
    """A single detected blocker that prevents or degrades mission execution."""
    code:        str              # e.g. "MISSING_RESEARCH", "FAILED_TASK"
    description: str              # human-readable explanation
    severity:    BlockerSeverity
    task_id:     Optional[str] = None  # which task caused this, if applicable

    @property
    def is_critical(self) -> bool:
        return self.severity == BlockerSeverity.critical


@dataclass
class MissionInformationGap:
    """A piece of information that is missing before the mission can execute."""
    field_name:  str           # e.g. "departure_date", "budget"
    description: str           # human-readable label
    category:    GapCategory

    def to_dict(self) -> dict:
        return {
            "field_name":  self.field_name,
            "description": self.description,
            "category":    self.category.value,
        }


@dataclass
class MissionNextAction:
    """The single recommended next action for a mission."""
    action:    str      # short imperative label, e.g. "Continue research"
    reasoning: str      # why this action is recommended
    priority:  int = 1  # 1=immediate, 2=soon, 3=eventually


@dataclass
class MissionWorkflowRecommendation:
    """
    Advisory recommendation for which workflow to launch.
    Advisory ONLY — does not trigger any workflow.
    """
    workflow_type: str    # e.g. "booking_workflow", "purchase_workflow"
    action_type:   str    # e.g. "book", "purchase" (intelligence.models.ActionType value)
    confidence:    float  # 0.0–1.0
    reasoning:     str


@dataclass
class MissionIntelligenceReport:
    """
    Complete advisory intelligence report for a mission.

    ADVISORY ONLY — this report never mutates Mission state,
    never triggers workflows, never grants approvals.
    All decisions remain with the human operator.
    """
    mission_id:             str
    readiness_score:        float                              # 0.0–1.0
    confidence:             float                              # overall intelligence confidence
    recommended_action:     str                                # short action label
    suggested_workflow:     Optional[str]                      # workflow_type or None
    blockers:               list[MissionBlocker]
    missing_information:    list[MissionInformationGap]
    reasoning:              str                                # human-readable explanation
    next_action:            MissionNextAction
    advisory_state:         MissionAdvisoryState
    workflow_recommendation: Optional[MissionWorkflowRecommendation]
    generated_at:           datetime = field(default_factory=datetime.utcnow)
    latency_ms:             int = 0
    # V6.0: optional tab coordination context (dict to avoid circular import)
    tab_context:            Optional[dict] = None
    # V6.5: optional trust evaluation fields (advisory only)
    trust_score:            Optional[float] = None
    risk_level:             Optional[str]   = None   # RiskLevel.value
    approval_required:      Optional[bool]  = None
    # V7.0: optional browser sync fields (advisory only)
    browser_activity_score: Optional[float] = None   # 0.0–1.0 freshness signal
    active_tab_count:       Optional[int]   = None
    recent_event_count:     Optional[int]   = None

    @property
    def critical_blockers(self) -> list[MissionBlocker]:
        return [b for b in self.blockers if b.is_critical]

    @property
    def is_blocked(self) -> bool:
        return bool(self.critical_blockers)

    @property
    def is_ready(self) -> bool:
        return self.readiness_score >= 0.80 and not self.is_blocked
