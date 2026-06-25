"""
V7.5 Integration Tests — Decision Center REST API (38 tests).
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.decisions import registry as reg
from app.decisions import analytics as anal
from app.decisions import timeline as tl
from app.decisions.models import (
    DecisionType, DecisionPriority, DecisionStatus, make_decision,
)
from app.mission.models import Mission
import app.mission.store as ms
import app.trust.registry as trust_reg
from app.trust import analytics as trust_analytics
from app.browser import analytics as bra
import app.browser.registry as ev_reg
from app.browser import timeline as btl
from app.tabs import registry as tab_reg

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset():
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()
    trust_reg._reset_for_testing()
    trust_analytics._reset_for_testing()
    bra._reset_for_testing()
    ev_reg._reset_for_testing()
    btl._reset_for_testing()
    tab_reg._reset_for_testing()
    yield
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()
    trust_reg._reset_for_testing()
    trust_analytics._reset_for_testing()
    bra._reset_for_testing()
    ev_reg._reset_for_testing()
    btl._reset_for_testing()
    tab_reg._reset_for_testing()


def _make_mission(title="Test") -> str:
    m = Mission(mission_id=str(uuid.uuid4()), title=title, objective="test")
    ms.put(m)
    return m.mission_id


def _add_decision(priority=DecisionPriority.medium, mission_id=None,
                  dec_type=DecisionType.info):
    d = make_decision(dec_type, priority, "Test Decision", "Description", "test_src",
                      mission_id=mission_id)
    reg.add(d)
    anal.record_created(priority.value)
    return d


# ── GET /decisions ─────────────────────────────────────────────────────────────

class TestListDecisions:
    def test_list_200(self):
        r = client.get("/decisions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_returns_added_decisions(self):
        _add_decision()
        _add_decision()
        r = client.get("/decisions")
        assert len(r.json()) >= 2

    def test_filter_by_mission(self):
        mid = _make_mission()
        _add_decision(mission_id=mid)
        _add_decision(mission_id="other-mission")
        r = client.get(f"/decisions?mission_id={mid}")
        assert r.status_code == 200
        items = r.json()
        assert all(d["mission_id"] == mid for d in items)

    def test_filter_by_status(self):
        d = _add_decision()
        reg.update_status(d.decision_id, DecisionStatus.resolved)
        r = client.get("/decisions?status=RESOLVED")
        assert r.status_code == 200
        items = r.json()
        assert all(dd["status"] == "RESOLVED" for dd in items)

    def test_filter_by_priority(self):
        _add_decision(DecisionPriority.critical)
        _add_decision(DecisionPriority.low)
        r = client.get("/decisions?priority=CRITICAL")
        assert r.status_code == 200
        items = r.json()
        assert all(dd["priority"] == "CRITICAL" for dd in items)

    def test_invalid_status_400(self):
        r = client.get("/decisions?status=NONSENSE")
        assert r.status_code == 400

    def test_invalid_priority_400(self):
        r = client.get("/decisions?priority=NONSENSE")
        assert r.status_code == 400

    def test_limit_respected(self):
        for _ in range(10):
            _add_decision()
        r = client.get("/decisions?limit=3")
        assert len(r.json()) <= 3

    def test_decision_schema_keys(self):
        _add_decision()
        r = client.get("/decisions")
        d = r.json()[0]
        for key in ("decision_id", "decision_type", "priority", "title",
                    "description", "source", "created_at", "status"):
            assert key in d


# ── GET /decisions/critical ───────────────────────────────────────────────────

class TestCriticalDecisions:
    def test_critical_200(self):
        r = client.get("/decisions/critical")
        assert r.status_code == 200

    def test_critical_only_returns_critical(self):
        _add_decision(DecisionPriority.critical, dec_type=DecisionType.trust_warning)
        _add_decision(DecisionPriority.high)
        r = client.get("/decisions/critical")
        items = r.json()
        assert all(d["priority"] == "CRITICAL" for d in items)
        assert len(items) >= 1

    def test_critical_empty_when_none(self):
        _add_decision(DecisionPriority.low)
        r = client.get("/decisions/critical")
        assert r.json() == []


# ── GET /decisions/analytics ──────────────────────────────────────────────────

class TestDecisionAnalyticsEndpoint:
    def test_analytics_200(self):
        r = client.get("/decisions/analytics")
        assert r.status_code == 200

    def test_analytics_fields(self):
        r = client.get("/decisions/analytics")
        body = r.json()
        for field in ("created", "acknowledged", "dismissed", "resolved",
                      "critical", "high", "medium", "low", "avg_resolution_ms"):
            assert field in body

    def test_analytics_counts_accumulate(self):
        _add_decision(DecisionPriority.high)
        _add_decision(DecisionPriority.critical)
        r = client.get("/decisions/analytics")
        body = r.json()
        assert body["created"]  >= 2
        assert body["high"]     >= 1
        assert body["critical"] >= 1


# ── GET /decisions/inspect ────────────────────────────────────────────────────

class TestDecisionInspect:
    def test_inspect_200(self):
        r = client.get("/decisions/inspect")
        assert r.status_code == 200

    def test_inspect_keys(self):
        r = client.get("/decisions/inspect")
        body = r.json()
        for key in ("active_count", "critical_count", "high_count",
                    "active_decisions", "critical_decisions", "source_breakdown",
                    "analytics", "registry_stats", "latency_ms"):
            assert key in body

    def test_inspect_reflects_added_items(self):
        _add_decision(DecisionPriority.critical)
        r = client.get("/decisions/inspect")
        assert r.json()["critical_count"] >= 1


# ── GET /decisions/{id} ───────────────────────────────────────────────────────

class TestGetDecision:
    def test_get_existing_200(self):
        d = _add_decision()
        r = client.get(f"/decisions/{d.decision_id}")
        assert r.status_code == 200
        assert r.json()["decision_id"] == d.decision_id

    def test_get_unknown_404(self):
        r = client.get("/decisions/nonexistent-decision-xyz")
        assert r.status_code == 404


# ── GET /decisions/mission/{id} ───────────────────────────────────────────────

class TestDecisionsForMission:
    def test_mission_decisions_200(self):
        mid = _make_mission()
        r = client.get(f"/decisions/mission/{mid}")
        assert r.status_code == 200

    def test_mission_decisions_filtered(self):
        mid = _make_mission()
        _add_decision(mission_id=mid)
        _add_decision(mission_id="other")
        r = client.get(f"/decisions/mission/{mid}")
        items = r.json()
        assert all(d["mission_id"] == mid for d in items)

    def test_unknown_mission_returns_empty(self):
        r = client.get("/decisions/mission/unknown-m")
        assert r.json() == []


# ── POST /decisions/aggregate/{mission_id} ────────────────────────────────────

class TestAggregateDecisions:
    def test_aggregate_existing_mission_200(self):
        mid = _make_mission()
        r = client.post(f"/decisions/aggregate/{mid}")
        assert r.status_code == 200

    def test_aggregate_response_schema(self):
        mid = _make_mission()
        r = client.post(f"/decisions/aggregate/{mid}")
        body = r.json()
        assert "mission_id"       in body
        assert "decisions_found"  in body
        assert "decisions"        in body
        assert body["mission_id"] == mid

    def test_aggregate_unknown_mission_404(self):
        r = client.post("/decisions/aggregate/no-such-mission-xyz")
        assert r.status_code == 404

    def test_aggregate_stores_in_registry(self):
        mid = _make_mission()
        r = client.post(f"/decisions/aggregate/{mid}")
        body = r.json()
        if body["decisions_found"] > 0:
            first_id = body["decisions"][0]["decision_id"]
            stored = reg.get(first_id)
            assert stored is not None


# ── POST /decisions/{id}/acknowledge ─────────────────────────────────────────

class TestAcknowledgeDecision:
    def test_acknowledge_200(self):
        d = _add_decision()
        r = client.post(f"/decisions/{d.decision_id}/acknowledge")
        assert r.status_code == 200
        assert r.json()["status"] == "ACKNOWLEDGED"

    def test_acknowledge_updates_registry(self):
        d = _add_decision()
        client.post(f"/decisions/{d.decision_id}/acknowledge")
        updated = reg.get(d.decision_id)
        assert updated.status == DecisionStatus.acknowledged

    def test_acknowledge_unknown_404(self):
        r = client.post("/decisions/nonexistent-xyz/acknowledge")
        assert r.status_code == 404

    def test_acknowledge_increments_analytics(self):
        anal._reset_for_testing()
        d = _add_decision()
        client.post(f"/decisions/{d.decision_id}/acknowledge")
        assert anal.get_analytics()["acknowledged"] == 1


# ── POST /decisions/{id}/dismiss ─────────────────────────────────────────────

class TestDismissDecision:
    def test_dismiss_200(self):
        d = _add_decision()
        r = client.post(f"/decisions/{d.decision_id}/dismiss")
        assert r.status_code == 200
        assert r.json()["status"] == "DISMISSED"

    def test_dismiss_updates_registry(self):
        d = _add_decision()
        client.post(f"/decisions/{d.decision_id}/dismiss")
        updated = reg.get(d.decision_id)
        assert updated.status == DecisionStatus.dismissed
        assert updated.dismissed_at is not None

    def test_dismiss_unknown_404(self):
        r = client.post("/decisions/nonexistent-xyz/dismiss")
        assert r.status_code == 404


# ── POST /decisions/{id}/resolve ─────────────────────────────────────────────

class TestResolveDecision:
    def test_resolve_200(self):
        d = _add_decision()
        r = client.post(f"/decisions/{d.decision_id}/resolve")
        assert r.status_code == 200
        assert r.json()["status"] == "RESOLVED"

    def test_resolve_updates_registry(self):
        d = _add_decision()
        client.post(f"/decisions/{d.decision_id}/resolve")
        updated = reg.get(d.decision_id)
        assert updated.status == DecisionStatus.resolved
        assert updated.resolved_at is not None

    def test_resolve_increments_analytics(self):
        anal._reset_for_testing()
        d = _add_decision()
        client.post(f"/decisions/{d.decision_id}/resolve")
        assert anal.get_analytics()["resolved"] == 1

    def test_resolve_unknown_404(self):
        r = client.post("/decisions/nonexistent-xyz/resolve")
        assert r.status_code == 404


# ── Mission inspect integration (V7.5 decisions field) ───────────────────────

class TestMissionInspectDecisions:
    def test_mission_inspect_has_decisions_field(self):
        mid = _make_mission()
        r = client.get(f"/mission/{mid}/inspect")
        assert r.status_code == 200
        assert "decisions" in r.json()

    def test_mission_inspect_decisions_structure(self):
        mid = _make_mission()
        _add_decision(mission_id=mid)
        r = client.get(f"/mission/{mid}/inspect")
        body = r.json()
        dec = body.get("decisions")
        if dec:  # populated only if decisions exist
            assert "total_decisions"  in dec
            assert "active_decisions" in dec
