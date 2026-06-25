"""
V6.5 Trust Engine — Pydantic Schemas.

REST serialization only. All domain logic lives in app/trust/*.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TrustEvaluationSchema(BaseModel):
    evaluation_id:     str
    target_type:       str
    target_id:         str
    trust_score:       float
    risk_level:        str
    approval_required: bool
    confidence:        float
    reasoning:         str
    created_at:        datetime

    model_config = {"from_attributes": True}


class TrustDecisionContractSchema(BaseModel):
    contract_id:              str
    evaluation_id:            str
    allowed_without_approval: bool
    requires_user_approval:   bool
    risk_level:               str
    trust_score:              float

    model_config = {"from_attributes": True}


class TrustAnalyticsSchema(BaseModel):
    trust_evaluations:    int
    low_risk:             int
    medium_risk:          int
    high_risk:            int
    critical_risk:        int
    approval_recommended: int
    approval_required:    int
    avg_trust_score:      float

    model_config = {"from_attributes": True}


class TrustInspectorSchema(BaseModel):
    mission_id:         str
    mission_trust:      Optional[TrustEvaluationSchema] = None
    tab_trust:          Optional[TrustEvaluationSchema] = None
    workflow_trust:     Optional[TrustEvaluationSchema] = None
    overall_trust_score: float = 0.0
    overall_risk_level: str    = "MEDIUM"
    approval_required:  bool   = False

    model_config = {"from_attributes": True}


# ── Request models ────────────────────────────────────────────────────────────

class EvaluateActionRequest(BaseModel):
    action_type:     str
    action_id:       Optional[str] = None
    workflow_type:   Optional[str] = None
    readiness_score: float = 0.5
    blocker_count:   int   = 0


class EvaluateWorkflowRequest(BaseModel):
    workflow_type:          str
    workflow_id:            Optional[str] = None
    readiness_score:        float = 0.5
    critical_blocker_count: int   = 0
    missing_info_count:     int   = 0
    workflow_tab_present:   bool  = False


class EvaluateTabRequest(BaseModel):
    mission_id:   str
    tab_context:  Optional[dict] = None
    tab_findings: Optional[list] = None


class EvaluateMissionRequest(BaseModel):
    mission_id:           str
    readiness_score:      float = 0.0
    critical_blockers:    int   = 0
    missing_info_count:   int   = 0
    task_count:           int   = 0
    completed_task_count: int   = 0
    failed_task_count:    int   = 0
    tab_count:            int   = 0
    orphan_tab_count:     int   = 0
    workflow_tab_present: bool  = False
