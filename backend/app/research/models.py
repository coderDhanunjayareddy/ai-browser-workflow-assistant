"""
V3.5 Research Session Engine — core domain models.

Pure Python dataclasses. No Pydantic here — API serialization lives in
schemas/assist.py (ResearchReportSchema, ResearchSourceSchema).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ResearchStatus(str, Enum):
    active = "active"
    completed = "completed"
    failed = "failed"
    abandoned = "abandoned"


class SourceType(str, Enum):
    web = "web"
    page_context = "page_context"
    ai_knowledge = "ai_knowledge"


@dataclass
class ResearchSource:
    source_id: str
    title: str
    url: str
    source_type: SourceType
    snippet: str
    credibility_score: float = 0.7


@dataclass
class ResearchPlan:
    """
    Deterministic 4-stage research plan derived from topic and entities.
    queries: list of search strings to run against providers.
    """
    topic: str
    queries: list[str]
    stages: list[str] = field(default_factory=lambda: [
        "Define topic",
        "Gather evidence",
        "Analyze evidence",
        "Produce findings",
    ])


@dataclass
class ResearchReport:
    """Synthesized output from all collected sources."""
    executive_summary: str
    key_findings: list[str]
    supporting_evidence: list[dict]   # [{finding, source_title, source_url, is_conclusion}]
    risks: list[str]
    open_questions: list[str]
    recommended_actions: list[str]
    confidence_score: float = 0.7


@dataclass
class ResearchSession:
    """
    One research session per conversation.
    Persists across multiple turns within a backend process lifetime.
    V3.6 will add DB persistence — same pattern as CognitiveSession → V3.0.
    """
    session_id: str
    conversation_id: str
    topic: str
    goal_id: Optional[str] = None
    entities: list[str] = field(default_factory=list)
    status: ResearchStatus = ResearchStatus.active
    plan: Optional[ResearchPlan] = None
    sources: list[ResearchSource] = field(default_factory=list)
    report: Optional[ResearchReport] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    synthesis_count: int = 0
