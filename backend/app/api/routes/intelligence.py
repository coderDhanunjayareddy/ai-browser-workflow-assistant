"""
V4.0 Intelligence Layer REST endpoints.

GET  /intelligence/analytics   — counters from the intelligence analytics module
GET  /intelligence/opportunity  — test opportunity detection for a query (debug)
"""
from fastapi import APIRouter

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/analytics")
def get_intelligence_analytics() -> dict:
    """Return in-memory intelligence layer counters."""
    from app.intelligence import analytics
    return analytics.get_analytics()


@router.get("/opportunity")
def detect_opportunity(query: str) -> dict:
    """
    Debug endpoint: detect execution opportunity for a given query string.
    Useful for testing the intelligence layer without running the full research pipeline.
    """
    from app.intelligence.opportunity_detector import detector
    from app.intelligence.approval_advisor import advisor

    opp = detector.detect(query)
    approval = advisor.classify(opp, query)

    return {
        "query": query,
        "detected": opp.detected,
        "confidence": opp.confidence,
        "action_type": opp.action_type.value,
        "workflow_candidate": opp.workflow_candidate,
        "required_entities": opp.required_entities,
        "missing_information": opp.missing_information,
        "approval_level": approval.value,
        "raw_action_keywords": opp.raw_action_keywords,
    }
