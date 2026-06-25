"""
V7.5 Decision Center — Domain Models.

DecisionItem      : a single item that requires a human decision or awareness
DecisionType      : category of the decision
DecisionStatus    : lifecycle state
DecisionPriority  : urgency level
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class DecisionType(str, Enum):
    trust_warning  = "TRUST_WARNING"
    recommendation = "RECOMMENDATION"
    blocker        = "BLOCKER"
    opportunity    = "OPPORTUNITY"
    info           = "INFO"


class DecisionStatus(str, Enum):
    open         = "OPEN"
    acknowledged = "ACKNOWLEDGED"
    dismissed    = "DISMISSED"
    resolved     = "RESOLVED"


class DecisionPriority(str, Enum):
    low      = "LOW"
    medium   = "MEDIUM"
    high     = "HIGH"
    critical = "CRITICAL"


PRIORITY_ORDER = {
    DecisionPriority.critical: 4,
    DecisionPriority.high:     3,
    DecisionPriority.medium:   2,
    DecisionPriority.low:      1,
}


@dataclass
class DecisionItem:
    decision_id:   str
    decision_type: DecisionType
    priority:      DecisionPriority
    title:         str
    description:   str
    source:        str           # component that raised it, e.g. "trust_engine"
    created_at:    datetime
    status:        DecisionStatus         = DecisionStatus.open
    mission_id:    Optional[str]          = None
    task_id:       Optional[str]          = None
    resolved_at:   Optional[datetime]     = None
    acknowledged_at: Optional[datetime]   = None
    dismissed_at:  Optional[datetime]     = None
    metadata:      dict[str, Any]         = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id":    self.decision_id,
            "decision_type":  self.decision_type.value,
            "priority":       self.priority.value,
            "title":          self.title,
            "description":    self.description,
            "source":         self.source,
            "created_at":     self.created_at.isoformat(),
            "status":         self.status.value,
            "mission_id":     self.mission_id,
            "task_id":        self.task_id,
            "resolved_at":    self.resolved_at.isoformat() if self.resolved_at else None,
            "acknowledged_at":self.acknowledged_at.isoformat() if self.acknowledged_at else None,
            "dismissed_at":   self.dismissed_at.isoformat() if self.dismissed_at else None,
            "metadata":       self.metadata,
        }

    @property
    def is_active(self) -> bool:
        return self.status == DecisionStatus.open

    @property
    def priority_order(self) -> int:
        return PRIORITY_ORDER.get(self.priority, 0)


def make_decision(
    decision_type: DecisionType,
    priority:      DecisionPriority,
    title:         str,
    description:   str,
    source:        str,
    *,
    mission_id: Optional[str] = None,
    task_id:    Optional[str] = None,
    metadata:   Optional[dict] = None,
) -> DecisionItem:
    return DecisionItem(
        decision_id   = str(uuid.uuid4()),
        decision_type = decision_type,
        priority      = priority,
        title         = title,
        description   = description,
        source        = source,
        created_at    = datetime.utcnow(),
        status        = DecisionStatus.open,
        mission_id    = mission_id,
        task_id       = task_id,
        metadata      = metadata or {},
    )
