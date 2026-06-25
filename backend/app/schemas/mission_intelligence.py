"""
V5.5 Mission Intelligence Layer — Pydantic Schemas.

Used for REST serialization only. All domain logic lives in
app/mission/intelligence/*.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class MissionBlockerSchema(BaseModel):
    code:        str
    description: str
    severity:    str         # "CRITICAL" | "WARNING" | "INFO"
    task_id:     Optional[str] = None

    model_config = {"from_attributes": True}


class MissionInformationGapSchema(BaseModel):
    field_name:  str
    description: str
    category:    str         # GapCategory value

    model_config = {"from_attributes": True}


class MissionNextActionSchema(BaseModel):
    action:    str
    reasoning: str
    priority:  int

    model_config = {"from_attributes": True}


class MissionWorkflowRecommendationSchema(BaseModel):
    workflow_type: str
    action_type:   str
    confidence:    float
    reasoning:     str

    model_config = {"from_attributes": True}


class MissionIntelligenceReportSchema(BaseModel):
    mission_id:              str
    readiness_score:         float
    confidence:              float
    recommended_action:      str
    suggested_workflow:      Optional[str]
    blockers:                list[MissionBlockerSchema]
    missing_information:     list[MissionInformationGapSchema]
    reasoning:               str
    next_action:             MissionNextActionSchema
    advisory_state:          str
    workflow_recommendation: Optional[MissionWorkflowRecommendationSchema]
    generated_at:            datetime
    latency_ms:              int
    tab_context:             Optional[dict] = None   # V6.0 tab coordination context
    # V6.5 trust evaluation fields (advisory)
    trust_score:             Optional[float] = None
    risk_level:              Optional[str]   = None
    approval_required:       Optional[bool]  = None
    # V7.0 browser sync fields (advisory)
    browser_activity_score:  Optional[float] = None
    active_tab_count:        Optional[int]   = None
    recent_event_count:      Optional[int]   = None

    model_config = {"from_attributes": True}


class MissionReadinessSchema(BaseModel):
    mission_id:      str
    readiness_score: float
    advisory_state:  str
    blockers:        list[MissionBlockerSchema]

    model_config = {"from_attributes": True}


class MissionBlockersSchema(BaseModel):
    mission_id:    str
    blocker_count: int
    blockers:      list[MissionBlockerSchema]

    model_config = {"from_attributes": True}


class MissionNextActionResponseSchema(BaseModel):
    mission_id:  str
    next_action: MissionNextActionSchema

    model_config = {"from_attributes": True}


class MissionWorkflowRecommendationResponseSchema(BaseModel):
    mission_id:              str
    workflow_recommendation: Optional[MissionWorkflowRecommendationSchema]
    readiness_score:         float

    model_config = {"from_attributes": True}


class MissionIntelligenceAnalyticsSchema(BaseModel):
    intelligence_runs:        int
    cache_hits:               int
    cache_misses:             int
    cache_hit_rate:           float
    readiness_evaluations:    int
    avg_readiness_score:      float
    blocker_detections:       int
    total_blockers_found:     int
    avg_blockers_per_run:     float
    workflow_recommendations: int
    next_action_generations:  int
    avg_latency_ms:           float

    model_config = {"from_attributes": True}
