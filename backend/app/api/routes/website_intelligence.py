"""
Phase E — Website Intelligence REST API (additive, read-only).

  POST /website-intelligence/analyze                 → analyze posted HTML or a DOM snapshot
  GET  /website-intelligence/live/{execution_id}     → analyze the live browser session page
  GET  /website-intelligence/live/{execution_id}/{section}
        section ∈ tree | forms | tables | dialogs | navigation | registry | hints |
                  locators | summary

Read-only analysis. NO browser actions. The gateway/planner/adapter are unchanged.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.website_intelligence import analyzer as wi_analyzer
from app.website_intelligence import inspector as wi_inspector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/website-intelligence", tags=["website-intelligence"])

_SLICES = {
    "tree":       wi_inspector.semantic_tree,
    "forms":      wi_inspector.forms,
    "tables":     wi_inspector.tables,
    "dialogs":    wi_inspector.dialogs,
    "navigation": wi_inspector.navigation,
    "registry":   wi_inspector.registry,
    "hints":      wi_inspector.hints,
    "locators":   wi_inspector.locator_metadata,
    "summary":    wi_inspector.summary,
}


class AnalyzeRequest(BaseModel):
    html:     Optional[str]  = None
    snapshot: Optional[dict] = None
    url:      str            = ""
    title:    str            = ""


@router.post("/analyze")
def analyze(body: AnalyzeRequest):
    if body.html is None and body.snapshot is None:
        raise HTTPException(status_code=400, detail="provide either 'html' or 'snapshot'")
    if body.snapshot is not None:
        result = wi_analyzer.analyze(body.snapshot, url=body.url, title=body.title)
    else:
        result = wi_analyzer.analyze_html(body.html or "", url=body.url, title=body.title)
    return result.to_dict()


def _live_result(execution_id: str):
    from app.execution_gateway.browser import session as browser_session
    sess = browser_session.get(execution_id)
    if sess is None:
        raise HTTPException(status_code=404, detail=f"No live browser session for {execution_id}")
    try:
        page = sess.ensure_page()
    except Exception:
        raise HTTPException(status_code=409, detail="browser page unavailable")
    try:
        return wi_analyzer.analyze_live(page)
    except Exception as e:  # pragma: no cover - defensive
        # Playwright's SYNC API has greenlet thread-affinity: a live page created in the
        # execution thread cannot be evaluated from a web-server worker thread. Callers
        # in that situation should capture the snapshot in the page's thread and POST it
        # to /website-intelligence/analyze (pure-Python, thread-safe).
        if "thread" in str(e).lower() or "greenlet" in str(e).lower():
            raise HTTPException(
                status_code=409,
                detail="live page not evaluable from this thread; capture the DOM in the "
                       "page's owning thread and POST it to /website-intelligence/analyze")
        raise HTTPException(status_code=500, detail=f"analysis failed: {e}")


@router.get("/live/{execution_id}")
def analyze_live(execution_id: str):
    return _live_result(execution_id).to_dict()


@router.get("/live/{execution_id}/{section}")
def analyze_live_section(execution_id: str, section: str):
    if section not in _SLICES:
        raise HTTPException(status_code=400, detail=f"unknown section: {section}; "
                            f"expected one of {sorted(_SLICES)}")
    result = _live_result(execution_id)
    return {"execution_id": execution_id, "section": section, "data": _SLICES[section](result)}
