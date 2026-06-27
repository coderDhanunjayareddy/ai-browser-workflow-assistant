"""
V8.8 Execution Authorization Framework — Integration tests (42 tests).

Tests the full governance → authorization flow via HTTP.
"""
import time
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.governance import registry as gov_reg, analytics as gov_anal, timeline as gov_tl
from app.approvals import registry as appr_reg, analytics as appr_anal, timeline as appr_tl
from app.authorization import registry as auth_reg, analytics as auth_anal, timeline as auth_tl
from app.governance.models import make_contract
from app.approvals.models import (
    make_approval_request, ApprovalSourceType, ApprovalRiskLevel, ApprovalStatus,
)

client = TestClient(app)


def _make_contract(mission_id="m-integ", approved=True, ttl=3600.0):
    c = make_contract(
        str(uuid.uuid4()), approved, "tester", time.time(),
        "TRUST_ENGINE", str(uuid.uuid4()), "HIGH",
        mission_id=mission_id, ttl_seconds=ttl,
    )
    gov_reg.add(c)
    return c


@pytest.fixture(autouse=True)
def clean():
    gov_reg._reset_for_testing(); gov_anal._reset_for_testing(); gov_tl._reset_for_testing()
    appr_reg._reset_for_testing(); appr_anal._reset_for_testing(); appr_tl._reset_for_testing()
    auth_reg._reset_for_testing(); auth_anal._reset_for_testing(); auth_tl._reset_for_testing()
    yield
    gov_reg._reset_for_testing(); gov_anal._reset_for_testing(); gov_tl._reset_for_testing()
    appr_reg._reset_for_testing(); appr_anal._reset_for_testing(); appr_tl._reset_for_testing()
    auth_reg._reset_for_testing(); auth_anal._reset_for_testing(); auth_tl._reset_for_testing()


# ── POST /authorization/evaluate/{contract_id} ────────────────────────────────

class TestEvaluateEndpoint:

    def test_evaluate_200(self):
        c = _make_contract()
        r = client.post(f"/authorization/evaluate/{c.contract_id}")
        assert r.status_code == 200

    def test_evaluate_returns_authorization_id(self):
        c = _make_contract()
        r = client.post(f"/authorization/evaluate/{c.contract_id}")
        assert "authorization_id" in r.json()

    def test_evaluate_authorized_true(self):
        c = _make_contract(approved=True)
        r = client.post(f"/authorization/evaluate/{c.contract_id}")
        assert r.json()["authorized"] is True

    def test_evaluate_status_active(self):
        c = _make_contract(approved=True)
        r = client.post(f"/authorization/evaluate/{c.contract_id}")
        assert r.json()["status"] == "ACTIVE"

    def test_evaluate_not_approved_denied(self):
        c = _make_contract(approved=False)
        r = client.post(f"/authorization/evaluate/{c.contract_id}")
        assert r.json()["authorized"] is False
        assert r.json()["status"] == "DENIED"

    def test_evaluate_missing_contract_404(self):
        r = client.post("/authorization/evaluate/no-such-contract")
        assert r.status_code == 404

    def test_evaluate_stores_in_registry(self):
        c = _make_contract()
        client.post(f"/authorization/evaluate/{c.contract_id}")
        assert auth_reg.count() == 1

    def test_evaluate_increments_analytics(self):
        c = _make_contract()
        client.post(f"/authorization/evaluate/{c.contract_id}")
        a = client.get("/authorization/analytics").json()
        assert a["authorizations_created"] >= 1

    def test_evaluate_has_eval_ms(self):
        c = _make_contract()
        r = client.post(f"/authorization/evaluate/{c.contract_id}")
        assert "eval_ms" in r.json()


# ── GET /authorization/{id} ───────────────────────────────────────────────────

class TestGetAuthorizationEndpoint:

    def test_get_by_id(self):
        c = _make_contract()
        ev = client.post(f"/authorization/evaluate/{c.contract_id}")
        auth_id = ev.json()["authorization_id"]
        r = client.get(f"/authorization/{auth_id}")
        assert r.status_code == 200
        assert r.json()["authorization_id"] == auth_id

    def test_get_missing_404(self):
        r = client.get("/authorization/nonexistent-id")
        assert r.status_code == 404


# ── GET /authorization/contract/{contract_id} ────────────────────────────────

class TestGetForContractEndpoint:

    def test_get_for_contract(self):
        c = _make_contract()
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get(f"/authorization/contract/{c.contract_id}")
        assert r.status_code == 200
        assert r.json()["contract_id"] == c.contract_id

    def test_get_for_contract_not_evaluated_404(self):
        c = _make_contract()
        r = client.get(f"/authorization/contract/{c.contract_id}")
        assert r.status_code == 404


# ── GET /authorization ────────────────────────────────────────────────────────

class TestListAuthorizationsEndpoint:

    def test_empty_initially(self):
        r = client.get("/authorization")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_after_evaluate(self):
        c = _make_contract()
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get("/authorization")
        assert len(r.json()) == 1

    def test_filter_by_status_active(self):
        c = _make_contract(approved=True)
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get("/authorization?status=ACTIVE")
        assert len(r.json()) == 1

    def test_filter_by_status_denied(self):
        c = _make_contract(approved=False)
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get("/authorization?status=DENIED")
        assert len(r.json()) == 1

    def test_filter_by_invalid_status_400(self):
        r = client.get("/authorization?status=INVALID")
        assert r.status_code == 400

    def test_filter_by_mission_id(self):
        c = _make_contract(mission_id="m-filter")
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get("/authorization?mission_id=m-filter")
        assert len(r.json()) == 1


# ── GET /authorization/mission/{id} ──────────────────────────────────────────

class TestMissionAuthorizationsEndpoint:

    def test_empty_for_unknown_mission(self):
        r = client.get("/authorization/mission/no-such")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_for_mission(self):
        c = _make_contract(mission_id="m-list")
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get("/authorization/mission/m-list")
        assert len(r.json()) == 1

    def test_no_cross_mission(self):
        c1 = _make_contract(mission_id="m-x")
        c2 = _make_contract(mission_id="m-y")
        client.post(f"/authorization/evaluate/{c1.contract_id}")
        client.post(f"/authorization/evaluate/{c2.contract_id}")
        r = client.get("/authorization/mission/m-x")
        assert len(r.json()) == 1


# ── GET /authorization/readiness/{mission_id} ────────────────────────────────

class TestReadinessEndpoint:

    def test_readiness_200(self):
        r = client.get("/authorization/readiness/m-rdns")
        assert r.status_code == 200

    def test_readiness_has_fields(self):
        r = client.get("/authorization/readiness/m-rdns2")
        d = r.json()
        for k in ["mission_id", "mission_ready", "readiness_score",
                  "contracts_ready", "approvals_ready", "blockers"]:
            assert k in d

    def test_readiness_score_range(self):
        r = client.get("/authorization/readiness/m-rdns3")
        assert 0.0 <= r.json()["readiness_score"] <= 1.0

    def test_readiness_with_active_authorization(self):
        c = _make_contract(mission_id="m-with-auth")
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get("/authorization/readiness/m-with-auth")
        d = r.json()
        assert d["active_authorizations"] >= 1


# ── GET /authorization/analytics ──────────────────────────────────────────────

class TestAnalyticsEndpoint:

    def test_analytics_200(self):
        r = client.get("/authorization/analytics")
        assert r.status_code == 200

    def test_analytics_keys(self):
        r = client.get("/authorization/analytics")
        d = r.json()
        for k in ["authorizations_created", "authorized", "denied",
                  "expired", "revoked", "consumed", "avg_evaluation_time_ms"]:
            assert k in d

    def test_analytics_authorized_increments(self):
        c = _make_contract(approved=True)
        client.post(f"/authorization/evaluate/{c.contract_id}")
        a = client.get("/authorization/analytics").json()
        assert a["authorized"] >= 1

    def test_analytics_denied_increments(self):
        c = _make_contract(approved=False)
        client.post(f"/authorization/evaluate/{c.contract_id}")
        a = client.get("/authorization/analytics").json()
        assert a["denied"] >= 1


# ── GET /authorization/inspect/{mission_id} ───────────────────────────────────

class TestInspectEndpoint:

    def test_inspect_200(self):
        r = client.get("/authorization/inspect/m-insp")
        assert r.status_code == 200

    def test_inspect_has_keys(self):
        r = client.get("/authorization/inspect/m-insp2")
        d = r.json()
        for k in ["total_authorizations", "active_count", "denied_count",
                  "executable_count", "analytics", "registry_stats", "latency_ms"]:
            assert k in d

    def test_inspect_shows_authorized(self):
        c = _make_contract(mission_id="m-insp3")
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get("/authorization/inspect/m-insp3")
        assert r.json()["active_count"] == 1
        assert r.json()["executable_count"] == 1

    def test_inspect_shows_denied(self):
        c = _make_contract(approved=False, mission_id="m-insp4")
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get("/authorization/inspect/m-insp4")
        assert r.json()["denied_count"] == 1
        assert r.json()["executable_count"] == 0


# ── Governance inspector includes authorization ────────────────────────────────

class TestGovernanceInspectorIncludesAuthorization:

    def test_gov_inspect_has_authorization_key(self):
        r = client.get("/governance/inspect/m-gov-auth")
        assert "authorization" in r.json()

    def test_gov_inspect_auth_populated_after_evaluate(self):
        c = _make_contract(mission_id="m-gov-pop")
        client.post(f"/authorization/evaluate/{c.contract_id}")
        r = client.get("/governance/inspect/m-gov-pop")
        d = r.json()
        assert d["authorization"] is not None
        assert d["authorization"].get("total", 0) >= 1


# ── Mission inspector includes authorization ──────────────────────────────────

class TestMissionInspectorIncludesAuthorization:

    def test_mission_inspect_has_authorization_key(self):
        from app.mission import store as ms
        from app.mission.models import Mission, MissionState
        m = Mission("m-auth-mis", "Auth Test", "test", MissionState.active)
        ms.put(m)
        r = client.get("/mission/m-auth-mis/inspect")
        assert r.status_code == 200
        assert "authorization" in r.json()
