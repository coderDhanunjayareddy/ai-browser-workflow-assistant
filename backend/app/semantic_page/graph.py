from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.contracts.versions import SEMANTIC_PAGE_GRAPH_V1
from app.semantic_page.serializers import stable_json


NodeType = Literal[
    "page",
    "section",
    "result_set",
    "result_item",
    "entity",
    "fact",
    "form",
    "field",
    "control",
    "navigation",
    "dialog",
    "table",
    "row",
    "download",
    "upload",
    "error_state",
    "visual_region",
]

EdgeType = Literal[
    "contains",
    "labels",
    "describes",
    "links_to",
    "controls",
    "submits",
    "filters",
    "sorts",
    "paginates",
    "represents",
    "has_fact",
    "source_of",
    "visually_near",
    "alternative_locator",
]


class SemanticNode(BaseModel):
    node_id: str
    node_type: NodeType
    label: str = ""
    text: str = ""
    selector: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticEdge(BaseModel):
    edge_id: str
    edge_type: EdgeType
    source_id: str
    target_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticFact(BaseModel):
    fact_id: str
    label: str
    value: str
    source_node_id: str | None = None
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticTarget(BaseModel):
    target_id: str
    target_type: str
    semantic_role: str
    label: str
    entity_ref: str | None = None
    locator_candidates: list[str] = Field(default_factory=list)
    confidence: float = 0.8
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticPageGraph(BaseModel):
    schema_version: str = SEMANTIC_PAGE_GRAPH_V1
    graph_id: str
    observation_id: str
    builder_version: str = "v1"
    url: str
    title: str
    page_type: str
    nodes: list[SemanticNode] = Field(default_factory=list)
    edges: list[SemanticEdge] = Field(default_factory=list)
    facts: list[SemanticFact] = Field(default_factory=list)
    targets: list[SemanticTarget] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_stable_json(self) -> str:
        return stable_json(self.model_dump(mode="json"))
