"""
V8.5 Governance Layer — Pydantic API Schemas.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class GovernanceContractSchema(BaseModel):
    contract_id:       str
    approval_id:       str
    mission_id:        Optional[str] = None
    task_id:           Optional[str] = None
    created_at:        float
    expires_at:        float
    approved:          bool
    approved_by:       str
    approved_at:       float
    source_type:       str
    source_id:         str
    risk_level:        str
    contract_version:  str = "1.0"
    execution_allowed: bool = True
    execution_reason:  str = ""
    status:            str = "ACTIVE"
    revoked_at:        Optional[float] = None
    revoked_reason:    Optional[str]   = None
    consumed_at:       Optional[float] = None
    metadata:          dict[str, Any]  = Field(default_factory=dict)


class EligibilityResultSchema(BaseModel):
    eligible:    bool
    contract_id: str
    reason:      str
    checked_at:  float
    conditions:  dict[str, bool] = Field(default_factory=dict)


class ExecutionAuthorizationSchema(BaseModel):
    contract_id: str
    authorized:  bool
    reason:      str
    metadata:    dict[str, Any] = Field(default_factory=dict)


class GovernanceAnalyticsSchema(BaseModel):
    contracts_created:   int   = 0
    contracts_active:    int   = 0
    contracts_consumed:  int   = 0
    contracts_revoked:   int   = 0
    contracts_expired:   int   = 0
    avg_contract_age_ms: float = 0.0


class GovernanceInspectorSchema(BaseModel):
    mission_id:         Optional[str] = None
    total_contracts:    int = 0
    active_count:       int = 0
    expired_count:      int = 0
    revoked_count:      int = 0
    consumed_count:     int = 0
    execution_eligible: int = 0
    active_contracts:   list[dict] = Field(default_factory=list)
    eligible_contracts: list[dict] = Field(default_factory=list)
    source_breakdown:   dict[str, int] = Field(default_factory=dict)
    decision_context:   Optional[dict] = None
    trust_signals:      Optional[dict] = None
    mission_context:    Optional[dict] = None
    timeline_summary:   dict = Field(default_factory=dict)
    analytics:          dict = Field(default_factory=dict)
    registry_stats:     dict = Field(default_factory=dict)
    latency_ms:         float = 0.0


class GovernanceSummarySchema(BaseModel):
    total:              int = 0
    active_contracts:   int = 0
    expired_contracts:  int = 0
    revoked_contracts:  int = 0
    consumed_contracts: int = 0
    execution_eligible: int = 0


class RevokeRequest(BaseModel):
    reason: str = ""
