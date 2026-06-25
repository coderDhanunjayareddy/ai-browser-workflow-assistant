"""
ResearchEngine: orchestrates the full research pipeline for a single query.

Pipeline:
  1. Plan:    extract topic, build 3 queries (deterministic)
  2. Collect: run providers in order → page_context, duckduckgo, ai_knowledge (fallback)
  3. Synthesize: LLM call → ResearchReport
  4. Escalate: detect action keywords → build WorkflowHandoffPayload (optional)

Returns (ResearchSession, Optional[WorkflowHandoffPayload]).
"""
from __future__ import annotations

import logging
from typing import Optional

from app.research import session_manager, analytics
from app.research.models import ResearchSession, ResearchSource
from app.research.planner import create_plan
from app.research.providers.page_context import PageContextProvider
from app.research.providers.duckduckgo import DuckDuckGoProvider
from app.research.providers.ai_knowledge import AIKnowledgeProvider
from app.research.synthesizer import synthesize
from app.research.workflow_bridge import build_research_handoff
from app.cognitive_core.models import CognitiveSession
from app.schemas.assist import AssistRequest, WorkflowHandoffPayload

logger = logging.getLogger(__name__)

_DDG_MIN_SOURCES = 2   # trigger AIKnowledge fallback when DDG returns fewer


def run_research(
    request: AssistRequest,
    cognitive_session: CognitiveSession,
) -> tuple[ResearchSession, Optional[WorkflowHandoffPayload]]:
    """
    Run the full research pipeline. Returns (session, handoff_or_none).
    The session.report field is populated after synthesis.
    """
    plan = create_plan(request.message)
    rsession = session_manager.create_session(
        conversation_id=request.conversation_id,
        topic=plan.topic,
    )
    session_manager.attach_plan(rsession, plan)
    analytics.record_session_started()

    try:
        sources = _collect_sources(request, plan.queries)
        session_manager.add_sources(rsession, sources)

        # Analytics
        used_page = any(s.source_type.value == "page_context" for s in sources)
        used_ddg = any(s.source_type.value == "web" for s in sources)
        used_ai = any(s.source_type.value == "ai_knowledge" for s in sources)
        analytics.record_sources(
            len(sources),
            used_page_context=used_page,
            used_ddg=used_ddg,
            used_ai_knowledge=used_ai,
        )

        report = synthesize(plan.topic, rsession.sources)
        session_manager.attach_report(rsession, report)
        analytics.record_synthesis()
        analytics.record_session_completed()

    except Exception as exc:
        logger.error("Research pipeline failed for %r: %s", request.message, exc)
        session_manager.mark_failed(rsession)
        analytics.record_session_failed()
        raise

    # Workflow escalation check
    handoff = build_research_handoff(
        query=request.message,
        research_session=rsession,
        cognitive_session=cognitive_session,
    )
    if handoff:
        analytics.record_workflow_escalation()

    return rsession, handoff


def _collect_sources(request: AssistRequest, queries: list[str]) -> list[ResearchSource]:
    """
    Run the provider chain:
    1. PageContextProvider (current page — always runs)
    2. DuckDuckGoProvider (first query only)
    3. AIKnowledgeProvider (if DDG returned < _DDG_MIN_SOURCES)
    """
    sources: list[ResearchSource] = []

    # Page context
    page_provider = PageContextProvider()
    try:
        page_sources = page_provider.search_page(queries[0] if queries else "", request.read_view)
        sources.extend(page_sources)
    except Exception as exc:
        logger.warning("PageContextProvider failed: %s", exc)

    # DuckDuckGo — run on first query only to avoid rate limits
    ddg_provider = DuckDuckGoProvider()
    ddg_sources: list[ResearchSource] = []
    if queries:
        try:
            ddg_sources = ddg_provider.search(queries[0], max_results=5)
            sources.extend(ddg_sources)
        except Exception as exc:
            logger.warning("DuckDuckGoProvider failed: %s", exc)

    # AI knowledge fallback — fires when DDG gives insufficient results
    if len(ddg_sources) < _DDG_MIN_SOURCES and queries:
        ai_provider = AIKnowledgeProvider()
        try:
            ai_sources = ai_provider.search(queries[0], max_results=3)
            sources.extend(ai_sources)
        except Exception as exc:
            logger.warning("AIKnowledgeProvider failed: %s", exc)

    return sources
