"""
V8.0 Human Approval Center — Domain models.

ApprovalRequest  — the core record; PENDING → APPROVED/REJECTED/EXPIRED/CANCELLED
ApprovalDecisionContract — future-execution bridge (V9.x will consume this).

Approval Center is INFORMATIONAL ONLY. No execution. No autonomy. No dispatch.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any


class ApprovalStatus(str, Enum):
    pending   = "PENDING"
    approved  = "APPROVED"
    rejected  = "REJECTED"
    expired   = "EXPIRED"
    cancelled = "CANCELLED"


class ApprovalSourceType(str, Enum):
    trust_engine          = "TRUST_ENGINE"
    decision_center       = "DECISION_CENTER"
    mission_intelligence  = "MISSION_INTELLIGENCE"
    manual                = "MANUAL"


class ApprovalRiskLevel(str, Enum):
    low      = "LOW"
    medium   = "MEDIUM"
    high     = "HIGH"
    critical = "CRITICAL"


RISK_ORDER: dict[ApprovalRiskLevel, int] = {
    ApprovalRiskLevel.critical: 4,
    ApprovalRiskLevel.high:     3,
    ApprovalRiskLevel.medium:   2,
    ApprovalRiskLevel.low:      1,
}

DEFAULT_TTL_SECONDS: float = 86400.0   # 24 h default expiry


@dataclass
class ApprovalRequest:
    approval_id:  str
    source_type:  ApprovalSourceType
    source_id:    str            # id of the originating DecisionItem / trust eval
    title:        str
    description:  str
    risk_level:   ApprovalRiskLevel
    priority:     str            # "LOW" / "MEDIUM" / "HIGH" / "CRITICAL"
    created_at:   float          # time.time()
    expires_at:   float          # time.time() + TTL

    status:           ApprovalStatus      = ApprovalStatus.pending
    mission_id:       Optional[str]       = None
    task_id:          Optional[str]       = None
    resolved_at:      Optional[float]     = None
    resolved_by:      Optional[str]       = None
    rejection_reason: Optional[str]       = None
    metadata:         dict[str, Any]      = field(default_factory=dict)

    # ── computed properties ──────────────────────────────────────────────────

    @property
    def is_pending(self) -> bool:
        return self.status == ApprovalStatus.pending

    @property
    def is_expired_now(self) -> bool:
        """True when PENDING and past expires_at."""
        return self.status == ApprovalStatus.pending and time.time() > self.expires_at

    @property
    def is_critical(self) -> bool:
        return self.risk_level in (ApprovalRiskLevel.critical, ApprovalRiskLevel.high)

    @property
    def risk_order(self) -> int:
        return RISK_ORDER.get(self.risk_level, 0)

    def to_dict(self) -> dict:
        return {
            "approval_id":       self.approval_id,
            "source_type":       self.source_type.value,
            "source_id":         self.source_id,
            "title":             self.title,
            "description":       self.description,
            "risk_level":        self.risk_level.value,
            "priority":          self.priority,
            "created_at":        self.created_at,
            "expires_at":        self.expires_at,
            "status":            self.status.value,
            "mission_id":        self.mission_id,
            "task_id":           self.task_id,
            "resolved_at":       self.resolved_at,
            "resolved_by":       self.resolved_by,
            "rejection_reason":  self.rejection_reason,
            "metadata":          self.metadata,
        }


@dataclass
class ApprovalDecisionContract:
    """
    V8.0 future-execution bridge.

    Produced when a human approves or rejects an ApprovalRequest.
    V9.x will read these to determine what actions are sanctioned.
    Nothing is executed here — this is a record of human intent only.
    """
    approval_id:     str
    approved:        bool
    approved_at:     float          # time.time() at decision moment
    decision_source: str            # e.g. "human_via_api"
    mission_id:      Optional[str] = None
    metadata:        dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "approval_id":     self.approval_id,
            "approved":        self.approved,
            "approved_at":     self.approved_at,
            "decision_source": self.decision_source,
            "mission_id":      self.mission_id,
            "metadata":        self.metadata,
        }


def make_approval_request(
    source_type:  ApprovalSourceType,
    source_id:    str,
    title:        str,
    description:  str,
    risk_level:   ApprovalRiskLevel,
    *,
    priority:     str = "HIGH",
    mission_id:   Optional[str] = None,
    task_id:      Optional[str] = None,
    ttl_seconds:  float = DEFAULT_TTL_SECONDS,
    metadata:     Optional[dict] = None,
) -> ApprovalRequest:
    now = time.time()
    return ApprovalRequest(
        approval_id  = str(uuid.uuid4()),
        source_type  = source_type,
        source_id    = source_id,
        title        = title,
        description  = description,
        risk_level   = risk_level,
        priority     = priority.upper(),
        created_at   = now,
        expires_at   = now + ttl_seconds,
        mission_id   = mission_id,
        task_id      = task_id,
        metadata     = metadata or {},
    )
