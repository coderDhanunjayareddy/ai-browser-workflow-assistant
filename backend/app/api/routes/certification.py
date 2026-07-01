"""
Phase F — Certification & Reliability REST routes (additive, read-only).

  GET  /certification/scenarios                      → declared certification scenarios
  GET  /certification/reliability                    → reliability metrics (workflow + step)
  GET  /certification/failures                       → failure catalog
  POST /certification/run                            → run deterministic (mock) certification, return report
  GET  /certification/report                         → build a report from recorded results
  GET  /certification/workflow-trace/{execution_id}  → consolidated workflow trace
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.certification import scenarios as cert_scenarios
from app.certification import reliability as cert_reliability
from app.certification import failure_catalog as cert_failures
from app.certification import runner as cert_runner
from app.certification import report as cert_report
from app.certification import trace as cert_trace

router = APIRouter(prefix="/certification", tags=["certification"])


@router.get("/scenarios")
def list_scenarios():
    scs = cert_scenarios.build_scenarios()
    return {"count": len(scs), "scenarios": [s.to_dict() for s in scs]}


@router.get("/reliability")
def get_reliability():
    return cert_reliability.metrics()


@router.get("/failures")
def get_failures():
    return cert_failures.summary()


@router.post("/run")
def run_certification(real_browser: bool = Query(False)):
    """
    Run the certification suite. Default mock mode is deterministic and browser-free
    (certifies the planner+gateway+authorization pipeline). real_browser=True drives
    real chromium (only where Playwright is installed).
    """
    scs = cert_scenarios.build_scenarios()
    results = cert_runner.certify_all(scs, base_url="", real_browser=real_browser)
    return cert_report.build_report(results, scenarios=scs, mode="real" if real_browser else "mock")


@router.get("/report")
def get_report():
    scs = cert_scenarios.build_scenarios()
    # report from whatever reliability/catalog state has been recorded this process
    return cert_report.build_report([], scenarios=scs, mode="recorded")


@router.get("/workflow-trace/{execution_id}")
def get_workflow_trace(execution_id: str):
    if not cert_trace.has_trace(execution_id):
        raise HTTPException(status_code=404, detail=f"No workflow trace for {execution_id}")
    return cert_trace.workflow_trace(execution_id)
