"""
V6.5 Integration Tests — Trust Engine REST API (32 tests).
"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.trust import analytics as trust_analytics
import app.trust.registry as trust_reg
import app.mission.store as mission_store
from app.mission.models import Mission, MissionState


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset():
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()
    yield
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()


def _create_mission(title: str = "Test Mission") -> str:
    import uuid
    from app.mission.models import Mission
    m = Mission(mission_id=str(uuid.uuid4()), title=title, objective="test")
    mission_store.put(m)
    return m.mission_id


# ── GET /trust/evaluate ───────────────────────────────────────────────────────

class TestQuickEvaluate:
    def test_read_page_low(self):
        r = client.get("/trust/evaluate?action_type=read_page")
        assert r.status_code == 200
        body = r.json()
        assert body["risk_level"] == "LOW"

    def test_purchase_critical(self):
        r = client.get("/trust/evaluate?action_type=purchase")
        assert r.status_code == 200
        assert r.json()["risk_level"]        == "CRITICAL"
        assert r.json()["approval_required"] is True

    def test_delete_critical(self):
        r = client.get("/trust/evaluate?action_type=delete")
        assert r.json()["risk_level"] == "CRITICAL"

    def test_with_readiness_param(self):
        r = client.get("/trust/evaluate?action_type=click&readiness_score=0.9")
        assert r.status_code == 200
        assert r.json()["trust_score"] is not None

    def test_response_has_required_fields(self):
        r = client.get("/trust/evaluate?action_type=navigate")
        body = r.json()
        for field in ("risk_level", "trust_score", "approval_required", "confidence", "reasoning"):
            assert field in body, f"Missing field: {field}"

    def test_unknown_action_defaults_medium(self):
        r = client.get("/trust/evaluate?action_type=totally_unknown_xyz")
        assert r.status_code == 200
        assert r.json()["risk_level"] == "MEDIUM"

    def test_missing_action_type_422(self):
        r = client.get("/trust/evaluate")
        assert r.status_code == 422


# ── POST /trust/action ────────────────────────────────────────────────────────

class TestEvaluateAction:
    def test_basic_action(self):
        r = client.post("/trust/action", json={"action_type": "click"})
        assert r.status_code == 200
        assert r.json()["risk_level"] == "MEDIUM"

    def test_critical_action_approval(self):
        r = client.post("/trust/action", json={"action_type": "payment"})
        assert r.status_code == 200
        body = r.json()
        assert body["risk_level"]        == "CRITICAL"
        assert body["approval_required"] is True

    def test_workflow_context_elevates(self):
        r = client.post("/trust/action", json={
            "action_type":   "click",
            "workflow_type": "purchase_workflow",
        })
        assert r.json()["risk_level"] == "CRITICAL"

    def test_empty_action_type_422(self):
        r = client.post("/trust/action", json={})
        assert r.status_code == 422

    def test_action_with_blocker_count(self):
        r = client.post("/trust/action", json={
            "action_type":   "navigate",
            "blocker_count": 3,
        })
        body = r.json()
        assert body["trust_score"] < 1.0


# ── POST /trust/workflow ──────────────────────────────────────────────────────

class TestEvaluateWorkflow:
    def test_research_workflow_low(self):
        r = client.post("/trust/workflow", json={"workflow_type": "research_workflow"})
        assert r.status_code == 200
        assert r.json()["risk_level"] == "LOW"

    def test_purchase_workflow_critical(self):
        r = client.post("/trust/workflow", json={"workflow_type": "purchase_workflow"})
        body = r.json()
        assert body["risk_level"]        == "CRITICAL"
        assert body["approval_required"] is True

    def test_missing_workflow_type_422(self):
        r = client.post("/trust/workflow", json={})
        assert r.status_code == 422

    def test_readiness_score_accepted(self):
        r = client.post("/trust/workflow", json={
            "workflow_type":   "research_workflow",
            "readiness_score": 0.95,
        })
        assert r.status_code == 200
        assert r.json()["trust_score"] > 0.80


# ── POST /trust/tab ───────────────────────────────────────────────────────────

class TestEvaluateTab:
    def test_no_tabs_neutral(self):
        r = client.post("/trust/tab", json={"mission_id": "m-no-tabs"})
        assert r.status_code == 200
        body = r.json()
        assert body["risk_level"]        == "LOW"
        assert body["approval_required"] is False

    def test_with_tab_context(self):
        r = client.post("/trust/tab", json={
            "mission_id": "m1",
            "tab_context": {
                "tab_count": 2,
                "tab_summaries": [
                    {"tab_id": "t1", "url": "https://example.com", "role": "RESEARCH",
                     "state": "OPEN", "mission_id": "m1"},
                ]
            }
        })
        assert r.status_code == 200
        assert r.json()["trust_score"] >= 0.0

    def test_missing_mission_id_422(self):
        r = client.post("/trust/tab", json={})
        assert r.status_code == 422


# ── POST /trust/mission ───────────────────────────────────────────────────────

class TestEvaluateMission:
    def test_high_readiness_low_risk(self):
        r = client.post("/trust/mission", json={
            "mission_id":           "m-ready",
            "readiness_score":      0.95,
            "task_count":           4,
            "completed_task_count": 4,
        })
        assert r.status_code == 200
        assert r.json()["risk_level"] == "LOW"

    def test_failed_tasks_medium_or_higher(self):
        r = client.post("/trust/mission", json={
            "mission_id":        "m-failed",
            "readiness_score":   0.1,
            "task_count":        4,
            "failed_task_count": 4,
            "critical_blockers": 3,
        })
        body = r.json()
        assert body["risk_level"] in ("MEDIUM", "HIGH", "CRITICAL")

    def test_missing_mission_id_422(self):
        r = client.post("/trust/mission", json={"readiness_score": 0.5})
        assert r.status_code == 422


# ── GET /trust/analytics ──────────────────────────────────────────────────────

class TestTrustAnalyticsEndpoint:
    def test_initial_zero_counts(self):
        r = client.get("/trust/analytics")
        assert r.status_code == 200
        body = r.json()
        assert body["trust_evaluations"] == 0

    def test_counts_after_evaluations(self):
        client.post("/trust/action", json={"action_type": "purchase"})
        client.post("/trust/action", json={"action_type": "read_page"})
        r = client.get("/trust/analytics")
        body = r.json()
        assert body["trust_evaluations"] >= 2
        assert body["critical_risk"]     >= 1
        assert body["low_risk"]          >= 1

    def test_analytics_has_average_trust(self):
        client.post("/trust/action", json={"action_type": "navigate"})
        r = client.get("/trust/analytics")
        assert "avg_trust_score" in r.json()


# ── GET /trust/inspect/{mission_id} ──────────────────────────────────────────

class TestTrustInspect:
    def test_inspect_existing_mission(self):
        mid = _create_mission("Trust Inspect Mission")
        r = client.get(f"/trust/inspect/{mid}")
        assert r.status_code == 200
        body = r.json()
        assert "mission_id"          in body
        assert "mission_trust"       in body
        assert "tab_trust"           in body
        assert "overall_trust_score" in body
        assert "overall_risk_level"  in body
        assert "approval_required"   in body

    def test_inspect_unknown_mission_404(self):
        r = client.get("/trust/inspect/nonexistent-mission-xyz")
        assert r.status_code == 404

    def test_inspect_has_mission_trust_score(self):
        mid = _create_mission("Score Mission")
        r = client.get(f"/trust/inspect/{mid}")
        body = r.json()
        assert body["mission_trust"] is not None
        assert 0.0 <= body["mission_trust"]["trust_score"] <= 1.0

    def test_inspect_overall_risk_level(self):
        mid = _create_mission("Overall Risk Mission")
        r = client.get(f"/trust/inspect/{mid}")
        body = r.json()
        assert body["overall_risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_mission_inspector_has_trust_section(self):
        mid = _create_mission("Inspector Trust")
        r = client.get(f"/mission/{mid}/inspect")
        assert r.status_code == 200
        body = r.json()
        # V6.5 trust section is present (may be null if mission has no tasks)
        assert "trust" in body
