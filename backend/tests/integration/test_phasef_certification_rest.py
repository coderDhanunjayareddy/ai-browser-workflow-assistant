"""Phase F — Integration tests: certification REST API (additive, deterministic)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.certification import reliability, failure_catalog
from app.execution_gateway import registry as ereg, analytics as ganal, timeline as gtl, audit
from app.execution_planning import registry as plan_reg
from app.authorization import registry as auth_reg
from app.mission import store as mission_store
from app.execution_gateway.browser import monitor as mon, metrics as met, exec_timeline as etl

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean():
    mods = [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store, mon, met, etl,
            reliability, failure_catalog]
    for m in mods:
        m._reset_for_testing()
    yield
    for m in mods:
        m._reset_for_testing()


def test_routes_registered():
    routes = {r.path for r in app.routes}
    for p in ["/certification/scenarios", "/certification/reliability", "/certification/failures",
              "/certification/run", "/certification/report", "/certification/workflow-trace/{execution_id}"]:
        assert p in routes


def test_list_scenarios():
    r = client.get("/certification/scenarios")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 20
    assert all("scenario_id" in s for s in body["scenarios"])


def test_run_mock_certification():
    r = client.post("/certification/run")
    assert r.status_code == 200
    rep = r.json()
    assert rep["mode"] == "mock"
    assert rep["scenarios_total"] >= 20
    assert rep["pass_rate"] == 1.0
    assert "reliability" in rep and "recommendations" in rep


def test_reliability_endpoint():
    client.post("/certification/run")
    r = client.get("/certification/reliability")
    assert r.status_code == 200
    m = r.json()
    assert m["workflows_total"] >= 20
    for k in ["workflow_success_rate", "duration_ms", "category_success", "step_metrics"]:
        assert k in m


def test_failures_endpoint_empty_clean_run():
    client.post("/certification/run")
    r = client.get("/certification/failures")
    assert r.status_code == 200
    assert r.json()["total_distinct"] == 0   # mock pipeline run has no failures


def test_report_endpoint():
    r = client.get("/certification/report")
    assert r.status_code == 200
    assert "reliability" in r.json()


def test_workflow_trace_404_for_unknown():
    assert client.get("/certification/workflow-trace/no-such-exec").status_code == 404


def test_existing_routes_unbroken():
    # additive: prior phase routes still present
    routes = {r.path for r in app.routes}
    for p in ["/gateway/browser/diagnostics/{execution_id}", "/website-intelligence/analyze",
              "/mission/{mission_id}/inspect"]:
        assert p in routes
