from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolRoute(str, Enum):
    context_answer = "context_answer"
    structured_search = "structured_search"
    connector_api = "connector_api"
    isolated_browser = "isolated_browser"
    user_session_browser = "user_session_browser"
    native_messaging_handoff = "native_messaging_handoff"


class ToolRoutingRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4000)
    current_page_available: bool = False
    requires_current_login: bool = False
    requires_gui: bool = False
    requires_dynamic_rendering: bool = False
    untrusted_research: bool = False
    connector: Optional[str] = Field(default=None, max_length=80)
    connector_available: bool = False
    native_capability: Optional[str] = Field(default=None, max_length=80)


class RouteCandidate(BaseModel):
    route: ToolRoute
    risk_score: int
    adequate: bool
    reason: str


class ToolRouteTrace(BaseModel):
    trace_id: str
    task_summary: str
    selected_route: ToolRoute
    selected_risk_score: int
    explanation: str
    candidates: list[RouteCandidate]
    requires_user_handoff: bool = False
    isolation: Optional[dict[str, Any]] = None


class StructuredSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    max_results: int = Field(default=5, ge=1, le=10)


class ConnectorCallRequest(BaseModel):
    connector: str = Field(min_length=1, max_length=80)
    operation: str = Field(min_length=1, max_length=120)
    arguments: dict[str, Any] = Field(default_factory=dict)
    read_only: bool = True


class IsolatedResearchRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    objective: str = Field(default="Read this page", min_length=1, max_length=1000)
    timeout_ms: int = Field(default=15_000, ge=1_000, le=30_000)
