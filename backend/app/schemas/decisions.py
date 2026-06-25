"""
V7.5 Decision Center — Pydantic request/response schemas.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel


class DecisionItemSchema(BaseModel):
    decision_id:    str
    decision_type:  str
    priority:       str
    title:          str
    description:    str
    source:         str
    created_at:     str
    status:         str
    mission_id:     Optional[str] = None
    task_id:        Optional[str] = None
    resolved_at:    Optional[str] = None
    acknowledged_at:Optional[str] = None
    dismissed_at:   Optional[str] = None
    metadata:       dict[str, Any] = {}


class DecisionAnalyticsSchema(BaseModel):
    created:           int
    acknowledged:      int
    dismissed:         int
    resolved:          int
    critical:          int
    high:              int
    medium:            int
    low:               int
    avg_resolution_ms: float


class DecisionTimelineEventSchema(BaseModel):
    decision_id: str
    event_type:  str
    mission_id:  str
    priority:    str
    title:       str
    source:      str
    timestamp:   str


class DecisionInspectorSchema(BaseModel):
    mission_id:         Optional[str]
    active_count:       int
    critical_count:     int
    high_count:         int
    active_decisions:   list[dict]
    critical_decisions: list[dict]
    source_breakdown:   dict[str, int]
    trust_signals:      dict
    blockers:           list[str]
    timeline:           dict
    analytics:          dict
    registry_stats:     dict
    latency_ms:         int


class DecisionSummarySchema(BaseModel):
    """Embedded in MissionInspectorSchema."""
    total_decisions:    int
    active_decisions:   int
    critical_decisions: int
    recent_decisions:   list[dict]


class AggregateDecisionsRequest(BaseModel):
    mission_id: str
