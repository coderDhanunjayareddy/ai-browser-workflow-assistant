"""
V8.0 Human Approval Center — Pydantic API Schemas.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class ApprovalRequestSchema(BaseModel):
    approval_id:      str
    source_type:      str
    source_id:        str
    title:            str
    description:      str
    risk_level:       str
    priority:         str
    created_at:       float
    expires_at:       float
    status:           str
    mission_id:       Optional[str] = None
    task_id:          Optional[str] = None
    resolved_at:      Optional[float] = None
    resolved_by:      Optional[str] = None
    rejection_reason: Optional[str] = None
    metadata:         dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionContractSchema(BaseModel):
    approval_id:     str
    approved:        bool
    approved_at:     float
    decision_source: str
    mission_id:      Optional[str] = None
    metadata:        dict[str, Any] = Field(default_factory=dict)


class ApprovalAnalyticsSchema(BaseModel):
    created:         int = 0
    approved:        int = 0
    rejected:        int = 0
    expired:         int = 0
    cancelled:       int = 0
    critical:        int = 0
    high:            int = 0
    medium:          int = 0
    low:             int = 0
    avg_approval_ms: float = 0.0


class ApprovalInspectorSchema(BaseModel):
    mission_id:        Optional[str] = None
    pending_count:     int = 0
    approved_count:    int = 0
    rejected_count:    int = 0
    critical_pending:  int = 0
    pending_approvals: list[dict] = Field(default_factory=list)
    critical_approvals: list[dict] = Field(default_factory=list)
    source_breakdown:  dict[str, int] = Field(default_factory=dict)
    trust_signals:     Optional[dict] = None
    decision_context:  Optional[dict] = None
    mission_context:   Optional[dict] = None
    timeline_summary:  dict = Field(default_factory=dict)
    analytics:         dict = Field(default_factory=dict)
    registry_stats:    dict = Field(default_factory=dict)
    latency_ms:        float = 0.0


class ApprovalSummarySchema(BaseModel):
    total:    int = 0
    pending:  int = 0
    approved: int = 0
    rejected: int = 0
    critical: int = 0


class GenerateApprovalsRequest(BaseModel):
    mission_id: str


class ApproveRequest(BaseModel):
    decision_source: str = "human_via_api"


class RejectRequest(BaseModel):
    reason:          str = ""
    decision_source: str = "human_via_api"
