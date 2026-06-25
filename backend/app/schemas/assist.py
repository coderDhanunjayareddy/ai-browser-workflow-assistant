from typing import Any, Optional
from pydantic import BaseModel, Field


# ── Cognitive Core schema types (V2.6) ────────────────────────────────────────

class CognitiveEntitySchema(BaseModel):
    """Serializable form of cognitive_core.models.Entity for API responses."""
    id: str
    type: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    confidence: float = 1.0
    source_turn: int = 0


class WorkflowHandoffPayload(BaseModel):
    """
    Enriched context payload attached to AssistResponse when a handoff is
    triggered. Contains the goal, tracked entities, and conversation summary
    for the Workflow Engine to consume.

    V3.0: WorkflowOrchestrator will read this payload instead of raw query text.
    """
    query: str
    goal_text: Optional[str] = None
    goal_status: Optional[str] = None
    entities: list[CognitiveEntitySchema] = Field(default_factory=list)
    conversation_summary: str = ""
    turn_count: int = 0


# ── Page & request types ──────────────────────────────────────────────────────

class ReadView(BaseModel):
    url: str
    title: str
    favicon: str = ""
    headings: list[str] = Field(default_factory=list)
    content_blocks: list[dict] = Field(default_factory=list)
    visible_text: str = Field(default="", max_length=8000)
    selected_text: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class AssistRequest(BaseModel):
    conversation_id: str
    message: str = Field(min_length=1, max_length=4000)
    read_view: ReadView
    context_fingerprint: str = ""
    selection_scope: str = Field(default="page")


class StructuredSummary(BaseModel):
    tldr: str
    key_points: list[str] = Field(default_factory=list)
    entities: list[dict[str, str]] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)


class AssistHandoff(BaseModel):
    available: bool = False
    target: Optional[str] = None


class AssistMeta(BaseModel):
    tokens: int = 0
    latency_ms: int = 0
    cache_hit: bool = False
    context_chars: int = 0


# ── Research Engine schema types (V3.5) ──────────────────────────────────────

class ResearchSourceSchema(BaseModel):
    source_id: str
    title: str
    url: str
    source_type: str      # "web" | "page_context" | "ai_knowledge"
    snippet: str
    credibility_score: float


class ResearchReportSchema(BaseModel):
    executive_summary: str
    key_findings: list[str] = Field(default_factory=list)
    supporting_evidence: list[dict] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    confidence_score: float = 0.7
    sources: list[ResearchSourceSchema] = Field(default_factory=list)
    session_id: str = ""
    topic: str = ""


# ── Intelligence Layer schema types (V4.0) ───────────────────────────────────

class ExecutionOpportunitySchema(BaseModel):
    detected: bool
    confidence: float
    action_type: str
    required_entities: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    workflow_candidate: bool = False


class WorkflowReadinessSchema(BaseModel):
    state: str           # "READY" | "PARTIALLY_READY" | "BLOCKED"
    ready_entities: list[str] = Field(default_factory=list)
    missing_entities: list[str] = Field(default_factory=list)
    blocking_reason: Optional[str] = None
    readiness_score: float = 0.0


class GoalNodeSchema(BaseModel):
    node_id: str
    text: str
    parent_id: Optional[str] = None
    children: list[str] = Field(default_factory=list)
    is_leaf: bool = False


class GoalTreeSchema(BaseModel):
    root_id: str
    nodes: dict[str, GoalNodeSchema] = Field(default_factory=dict)
    depth: int = 0
    leaf_count: int = 0


class ExecutionPlanSchema(BaseModel):
    plan_id: str
    goal: str
    workflow_type: str
    required_inputs: list[str] = Field(default_factory=list)
    inferred_inputs: dict[str, str] = Field(default_factory=dict)
    missing_inputs: list[str] = Field(default_factory=list)
    confidence: float
    recommended_next_action: str
    approval_level: str        # "SAFE" | "REQUIRES_APPROVAL" | "HIGH_RISK"


class WorkflowRecommendationSchema(BaseModel):
    recommendation_id: str
    action: str
    readiness: str             # ReadinessState value
    confidence: float
    approval_level: str
    plan_id: str


class BootstrapFactsSchema(BaseModel):
    query: str
    goal_text: Optional[str] = None
    workflow_type: str
    goal_tree_summary: list[str] = Field(default_factory=list)
    pre_filled_entities: dict[str, str] = Field(default_factory=dict)
    research_topic: str = ""
    research_summary: str = ""
    confidence: float = 0.0
    approval_level: str = "SAFE"


class IntelligenceLayerSchema(BaseModel):
    """Top-level intelligence result attached to AssistResponse."""
    opportunity: ExecutionOpportunitySchema
    readiness: Optional[WorkflowReadinessSchema] = None
    execution_plan: Optional[ExecutionPlanSchema] = None
    goal_tree: Optional[GoalTreeSchema] = None
    recommendations: list[WorkflowRecommendationSchema] = Field(default_factory=list)
    bootstrap_facts: Optional[BootstrapFactsSchema] = None
    latency_ms: int = 0


class AssistResponse(BaseModel):
    conversation_id: str
    intent: str
    routed_to: str
    type: str
    content: Any
    citations: list = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)
    handoff: AssistHandoff = Field(default_factory=AssistHandoff)
    meta: AssistMeta = Field(default_factory=AssistMeta)
    handoff_payload: Optional[WorkflowHandoffPayload] = None  # V2.6 Cognitive Core
    research_report: Optional[ResearchReportSchema] = None    # V3.5 Research Engine
    intelligence: Optional[IntelligenceLayerSchema] = None    # V4.0 Intelligence Layer
    task_id: Optional[str] = None                             # V4.5 Unified Task Graph
    task_state: Optional[str] = None                          # V4.5 Unified Task Graph
