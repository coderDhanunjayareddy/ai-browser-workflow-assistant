from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MissionBlueprintNodeSchema(BaseModel):
    node_id: str
    objective: str
    kind: str
    state: str
    priority: int
    owner_capabilities: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    evidence_requirements: list[dict[str, Any]] = Field(default_factory=list)
    expansion_rules: list[dict[str, Any]] = Field(default_factory=list)
    clarification_requirements: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionBlueprintDependencySchema(BaseModel):
    dependency_id: str
    from_node_id: str
    to_node_id: str
    kind: str
    required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class MissionBlueprintSchema(BaseModel):
    blueprint_id: str
    mission_id: str
    objective: str
    schema_version: str
    revision: int
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    recovery_rules: list[str] = Field(default_factory=list)
    termination_rules: list[str] = Field(default_factory=list)
    approval_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    mission_analysis: dict[str, Any] = Field(default_factory=dict)
    capability_requirements: dict[str, Any] = Field(default_factory=dict)
    risk_summary: dict[str, Any] = Field(default_factory=dict)
    clarification_requirements: list[dict[str, Any]] = Field(default_factory=list)
    dependency_graph: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    nodes: list[MissionBlueprintNodeSchema] = Field(default_factory=list)
    dependencies: list[MissionBlueprintDependencySchema] = Field(default_factory=list)


class MissionBlueprintNodesResponse(BaseModel):
    mission_id: str
    revision: int | None = None
    nodes: list[MissionBlueprintNodeSchema]


class MissionBlueprintRevisionSummary(BaseModel):
    revision_id: str
    blueprint_id: str
    mission_id: str
    revision: int
    reason: str
    created_by: str
    created_at: str | None = None


class MissionBlueprintRevisionsResponse(BaseModel):
    mission_id: str
    revisions: list[MissionBlueprintRevisionSummary]


class BlueprintNodeReadinessEvaluationSchema(BaseModel):
    node_id: str
    readiness: str
    expandable: bool
    dependency_reasons: list[str] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    blocking_reasons: list[str] = Field(default_factory=list)
    supporting_evidence: list[str] = Field(default_factory=list)
    critical_path: bool = False


class BlueprintReadinessSnapshotSchema(BaseModel):
    schema_version: str
    snapshot_id: str
    blueprint_id: str
    mission_id: str
    revision: int
    ready_nodes: list[str] = Field(default_factory=list)
    waiting_nodes: list[str] = Field(default_factory=list)
    blocked_nodes: list[str] = Field(default_factory=list)
    unreachable_nodes: list[str] = Field(default_factory=list)
    parallel_ready_nodes: list[str] = Field(default_factory=list)
    critical_path_ready_nodes: list[str] = Field(default_factory=list)
    evaluations: list[BlueprintNodeReadinessEvaluationSchema] = Field(default_factory=list)
    evidence_count: int
    created_at: str


class BlueprintReadinessSnapshotsResponse(BaseModel):
    mission_id: str
    snapshots: list[BlueprintReadinessSnapshotSchema]


class BlueprintExpansionSummarySchema(BaseModel):
    expansion_id: str
    blueprint_id: str
    mission_id: str
    blueprint_node_id: str
    blueprint_revision: int
    status: str
    generated_intent_ids: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None


class BlueprintExpansionsResponse(BaseModel):
    mission_id: str
    expanded_nodes: list[str] = Field(default_factory=list)
    pending_nodes: list[str] = Field(default_factory=list)
    generated_intent_ids: list[str] = Field(default_factory=list)
    expansions: list[BlueprintExpansionSummarySchema] = Field(default_factory=list)
