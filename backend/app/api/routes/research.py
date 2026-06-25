"""
V3.5 Research REST endpoints — session inspection and analytics.

GET  /research/session/{session_id}   — full session state for debugging
GET  /research/active/{conversation_id} — active session for a conversation
GET  /research/analytics              — counters from the research analytics module
"""
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/research", tags=["research"])


@router.get("/session/{session_id}")
def get_research_session(session_id: str) -> dict:
    """Return a serialized ResearchSession by its session_id."""
    from app.research import session_manager
    session = session_manager.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No research session found for session_id={session_id!r}",
        )
    return _serialize_session(session)


@router.get("/active/{conversation_id}")
def get_active_session(conversation_id: str) -> dict:
    """Return the active ResearchSession for a conversation, or 404 if none."""
    from app.research import session_manager
    session = session_manager.get_active(conversation_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No active research session for conversation_id={conversation_id!r}",
        )
    return _serialize_session(session)


@router.get("/analytics")
def get_research_analytics() -> dict:
    """Return in-memory research counters."""
    from app.research import analytics
    return analytics.get_analytics()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _serialize_session(session) -> dict:
    return {
        "session_id": session.session_id,
        "conversation_id": session.conversation_id,
        "topic": session.topic,
        "status": session.status.value,
        "synthesis_count": session.synthesis_count,
        "source_count": len(session.sources),
        "sources": [
            {
                "source_id": s.source_id,
                "title": s.title,
                "url": s.url,
                "source_type": s.source_type.value,
                "snippet": s.snippet[:200],
                "credibility_score": s.credibility_score,
            }
            for s in session.sources
        ],
        "report": _serialize_report(session.report) if session.report else None,
        "plan": {
            "topic": session.plan.topic,
            "queries": session.plan.queries,
            "stages": session.plan.stages,
        } if session.plan else None,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def _serialize_report(report) -> dict:
    return {
        "executive_summary": report.executive_summary,
        "key_findings": report.key_findings,
        "supporting_evidence": report.supporting_evidence,
        "risks": report.risks,
        "open_questions": report.open_questions,
        "recommended_actions": report.recommended_actions,
        "confidence_score": report.confidence_score,
    }
