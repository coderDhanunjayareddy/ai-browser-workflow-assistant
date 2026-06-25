"""
V4.0 Intelligence Layer — domain models.

Pure Python dataclasses. No Pydantic here — API serialization lives in
schemas/assist.py (IntelligenceLayerSchema and related types).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ActionType(str, Enum):
    """What kind of action the user intends to perform."""
    search = "search"
    book = "book"
    purchase = "purchase"
    register = "register"
    download = "download"
    schedule = "schedule"
    communicate = "communicate"
    navigate = "navigate"
    rent = "rent"
    apply = "apply"
    unknown = "unknown"


class ReadinessState(str, Enum):
    """How ready the workflow is to start."""
    ready = "READY"
    partially_ready = "PARTIALLY_READY"
    blocked = "BLOCKED"


class ApprovalLevel(str, Enum):
    """Safety classification for the detected action."""
    safe = "SAFE"
    requires_approval = "REQUIRES_APPROVAL"
    high_risk = "HIGH_RISK"


@dataclass
class ExecutionOpportunity:
    """Result from ExecutionOpportunityDetector."""
    detected: bool
    confidence: float
    action_type: ActionType
    required_entities: list[str]        # entity names required for this action
    missing_information: list[str]      # human-readable missing items
    workflow_candidate: bool            # True when the action maps to a known workflow type
    raw_action_keywords: list[str]      # which keywords triggered detection


@dataclass
class GoalNode:
    """Single node in a goal decomposition tree."""
    node_id: str
    text: str
    parent_id: Optional[str] = None
    children: list[str] = field(default_factory=list)
    is_leaf: bool = False


@dataclass
class GoalTree:
    """Hierarchical decomposition of the user's objective."""
    root_id: str
    nodes: dict[str, GoalNode] = field(default_factory=dict)
    depth: int = 0
    leaf_count: int = 0

    def get_root(self) -> Optional[GoalNode]:
        return self.nodes.get(self.root_id)

    def get_leaves(self) -> list[GoalNode]:
        return [n for n in self.nodes.values() if n.is_leaf]


@dataclass
class WorkflowReadiness:
    """Result from WorkflowReadinessAnalyzer."""
    state: ReadinessState
    ready_entities: list[str]           # entity names already in cognitive session
    missing_entities: list[str]         # required but not found
    blocking_reason: Optional[str]      # human-readable reason when BLOCKED
    readiness_score: float              # 0.0–1.0, fraction of required entities present


@dataclass
class ExecutionPlan:
    """Bridge object between research and workflow engine."""
    plan_id: str
    goal: str
    workflow_type: str                  # e.g. "flight_booking", "product_purchase"
    required_inputs: list[str]
    inferred_inputs: dict[str, str]     # entity_name → value inferred from session
    missing_inputs: list[str]
    confidence: float
    recommended_next_action: str
    approval_level: ApprovalLevel
    goal_tree: Optional[GoalTree] = None


@dataclass
class WorkflowRecommendation:
    """A single recommended action shown in the UI."""
    recommendation_id: str
    action: str                         # human-readable label
    readiness: ReadinessState
    confidence: float
    approval_level: ApprovalLevel
    plan_id: str                        # links to ExecutionPlan.plan_id


@dataclass
class BootstrapFacts:
    """
    Rich initialization context for the Workflow Engine.
    Much richer than WorkflowHandoffPayload — includes goal tree and inferred facts.
    """
    query: str
    goal_text: Optional[str]
    workflow_type: str
    goal_tree_summary: list[str]        # flattened leaf goals
    pre_filled_entities: dict[str, str] # name → value from cognitive session
    research_topic: str
    research_summary: str
    confidence: float
    approval_level: ApprovalLevel


@dataclass
class IntelligenceResult:
    """Top-level result from the intelligence engine — bundles all component outputs."""
    opportunity: ExecutionOpportunity
    goal_tree: Optional[GoalTree]
    readiness: Optional[WorkflowReadiness]
    execution_plan: Optional[ExecutionPlan]
    recommendations: list[WorkflowRecommendation]
    bootstrap_facts: Optional[BootstrapFacts]
    latency_ms: int = 0
