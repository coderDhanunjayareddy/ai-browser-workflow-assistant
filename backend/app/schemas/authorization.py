"""V8.8 Execution Authorization Framework — Pydantic API Schemas."""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class ExecutionAuthorizationSchema(BaseModel):
    authorization_id:     str
    contract_id:          str
    mission_id:           Optional[str] = None
    task_id:              Optional[str] = None
    evaluated_at:         float
    expires_at:           float
    authorized:           bool
    authorization_reason: str
    evaluator_version:    str = "1.0"
    risk_level:           str = "LOW"
    status:               str = "ACTIVE"
    trust_score:          Optional[float] = None
    conditions:           dict[str, bool] = Field(default_factory=dict)
    metadata:             dict[str, Any]  = Field(default_factory=dict)
    revoked_at:           Optional[float] = None
    revoked_reason:       Optional[str]   = None
    consumed_at:          Optional[float] = None
    is_executable:        bool = False


class ExecutionReadinessReportSchema(BaseModel):
    mission_id:            str
    mission_ready:         bool
    contracts_ready:       int = 0
    approvals_ready:       int = 0
    trust_ready:           bool = False
    blockers:              list[str] = Field(default_factory=list)
    readiness_score:       float = 0.0
    evaluated_at:          float = 0.0
    active_authorizations: int = 0
    denied_authorizations: int = 0
    executable_tasks:      list[str] = Field(default_factory=list)


class AuthorizationAnalyticsSchema(BaseModel):
    authorizations_created:  int   = 0
    authorized:              int   = 0
    denied:                  int   = 0
    expired:                 int   = 0
    revoked:                 int   = 0
    consumed:                int   = 0
    avg_evaluation_time_ms:  float = 0.0


class AuthorizationInspectorSchema(BaseModel):
    mission_id:               Optional[str] = None
    total_authorizations:     int = 0
    active_count:             int = 0
    denied_count:             int = 0
    expired_count:            int = 0
    revoked_count:            int = 0
    consumed_count:           int = 0
    executable_count:         int = 0
    active_authorizations:    list[dict] = Field(default_factory=list)
    executable_authorizations:list[dict] = Field(default_factory=list)
    risk_breakdown:           dict[str, int] = Field(default_factory=dict)
    mission_context:          Optional[dict] = None
    trust_signals:            Optional[dict] = None
    governance_context:       Optional[dict] = None
    readiness_report:         Optional[dict] = None
    timeline_summary:         dict = Field(default_factory=dict)
    analytics:                dict = Field(default_factory=dict)
    registry_stats:           dict = Field(default_factory=dict)
    latency_ms:               float = 0.0


class AuthorizationSummarySchema(BaseModel):
    total:                    int = 0
    active_authorizations:    int = 0
    denied_authorizations:    int = 0
    expired_authorizations:   int = 0
    revoked_authorizations:   int = 0
    consumed_authorizations:  int = 0
    executable_tasks:         list[str] = Field(default_factory=list)


class RevokeAuthorizationRequest(BaseModel):
    reason: str = ""
