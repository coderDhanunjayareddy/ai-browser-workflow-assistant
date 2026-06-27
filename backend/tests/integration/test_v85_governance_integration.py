"""
V8.5 Governance Layer — Integration tests (37 tests).

Tests the full approve→GovernanceContract flow via HTTP.
All state goes through the same singleton registries the app uses,
so approve endpoint → governance registry → eligibility endpoint all observe
the same in-memory contract.
"""
import time
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.approvals import registry as appr_reg
from app.approvals import analytics as appr_anal
from app.approvals import timeline as appr_tl
from app.governance import registry as gov_reg
from app.governance import analytics as gov_anal
from app.governance import timeline as gov_tl

client = TestClient(app)


def _make_approval(mission_id="m-integ", risk="HIGH"):
    from app.approvals.models import make_approval_request, ApprovalSourceType, ApprovalRiskLevel
    rl = ApprovalRiskLevel(risk)
    a = make_approval_request(
        source_type = ApprovalSourceType.trust_engine,
        source_id   = str(uuid.uuid4()),
        title       = "Integration Test Approval",
        description = "for testing",
        risk_level  = rl,
        priority    = "HIGH",
        mission_id  = mission_id,
    )
    appr_reg.add(a)
    return a


@pytest.fixture(autouse=True)
def clean():
    appr_reg._reset_for_testing()
    appr_anal._reset_for_testing()
    appr_tl._reset_for_testing()
    gov_reg._reset_for_testing()
    gov_anal._reset_for_testing()
    gov_tl._reset_for_testing()
    yield
    appr_reg._reset_for_testing()
    appr_anal._reset_for_testing()
    appr_tl._reset_for_testing()
    gov_reg._reset_for_testing()
    gov_anal._reset_for_testing()
    gov_tl._reset_for_testing()


# ── Approve endpoint now returns governance_contract ──────────────────────────

class TestApproveReturnsGovernanceContract:

    def test_approve_returns_governance_contract_key(self):
        a = _make_approval()
        r = client.post(f"/approvals/{a.approval_id}/approve")
        assert r.status_code == 200
        assert "governance_contract" in r.json()

    def test_governance_contract_not_none_after_approve(self):
        a = _make_approval()
        r = client.post(f"/approvals/{a.approval_id}/approve")
        data = r.json()
        assert data["governance_contract"] is not None

    def test_governance_contract_has_contract_id(self):
        a = _make_approval()
        r = client.post(f"/approvals/{a.approval_id}/approve")
        gc = r.json()["governance_contract"]
        assert "contract_id" in gc

    def test_governance_contract_approved_true(self):
        a = _make_approval()
        r = client.post(f"/approvals/{a.approval_id}/approve")
        gc = r.json()["governance_contract"]
        assert gc["approved"] is True

    def test_governance_contract_execution_allowed(self):
        a = _make_approval()
        r = client.post(f"/approvals/{a.approval_id}/approve")
        gc = r.json()["governance_contract"]
        assert gc["execution_allowed"] is True

    def test_governance_contract_status_active(self):
        a = _make_approval()
        r = client.post(f"/approvals/{a.approval_id}/approve")
        gc = r.json()["governance_contract"]
        assert gc["status"] == "ACTIVE"

    def test_governance_contract_mission_id_matches(self):
        a = _make_approval(mission_id="m-gc-check")
        r = client.post(f"/approvals/{a.approval_id}/approve")
        gc = r.json()["governance_contract"]
        assert gc["mission_id"] == "m-gc-check"

    def test_backward_compat_contract_field_still_present(self):
        a = _make_approval()
        r = client.post(f"/approvals/{a.approval_id}/approve")
        data = r.json()
        assert "contract" in data  # V8.0 backward compat

    def test_reject_has_no_governance_contract(self):
        a = _make_approval()
        r = client.post(f"/approvals/{a.approval_id}/reject")
        data = r.json()
        # reject should NOT produce a governance_contract key
        assert "governance_contract" not in data or data.get("governance_contract") is None


# ── Governance contract lands in registry ────────────────────────────────────

class TestGovernanceContractInRegistry:

    def test_contract_in_registry_after_approve(self):
        a = _make_approval()
        client.post(f"/approvals/{a.approval_id}/approve")
        contracts = gov_reg.list_all()
        assert len(contracts) == 1

    def test_contract_for_approval_lookup(self):
        a = _make_approval()
        r = client.post(f"/approvals/{a.approval_id}/approve")
        gc_id = r.json()["governance_contract"]["contract_id"]
        found = gov_reg.get(gc_id)
        assert found is not None

    def test_registry_count_one_after_approve(self):
        _make_approval(); _make_approval()
        for a_item in appr_reg.list_all():
            client.post(f"/approvals/{a_item.approval_id}/approve")
        assert gov_reg.count() == 2


# ── GET /governance/contracts ─────────────────────────────────────────────────

class TestGovernanceContractsListEndpoint:

    def test_list_empty_by_default(self):
        r = client.get("/governance/contracts")
        assert r.status_code == 200
        assert r.json() == []

    def test_list_after_approve(self):
        a = _make_approval()
        client.post(f"/approvals/{a.approval_id}/approve")
        r = client.get("/governance/contracts")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_filter_by_status_active(self):
        a = _make_approval()
        client.post(f"/approvals/{a.approval_id}/approve")
        r = client.get("/governance/contracts?status=ACTIVE")
        assert r.status_code == 200
        assert len(r.json()) == 1

    def test_filter_by_status_revoked_empty(self):
        a = _make_approval()
        client.post(f"/approvals/{a.approval_id}/approve")
        r = client.get("/governance/contracts?status=REVOKED")
        assert r.status_code == 200
        assert r.json() == []

    def test_filter_by_invalid_status_400(self):
        r = client.get("/governance/contracts?status=INVALID")
        assert r.status_code == 400

    def test_filter_by_mission_id(self):
        a = _make_approval(mission_id="m-filter")
        client.post(f"/approvals/{a.approval_id}/approve")
        r = client.get("/governance/contracts?mission_id=m-filter")
        assert r.status_code == 200
        assert len(r.json()) == 1


# ── GET /governance/contracts/active ─────────────────────────────────────────

class TestGovernanceActiveEndpoint:

    def test_empty_initially(self):
        r = client.get("/governance/contracts/active")
        assert r.status_code == 200
        assert r.json() == []

    def test_active_after_approve(self):
        a = _make_approval()
        client.post(f"/approvals/{a.approval_id}/approve")
        r = client.get("/governance/contracts/active")
        assert r.status_code == 200
        assert len(r.json()) == 1


# ── GET /governance/contracts/mission/{id} ───────────────────────────────────

class TestGovernanceMissionEndpoint:

    def test_empty_for_unknown_mission(self):
        r = client.get("/governance/contracts/mission/no-such")
        assert r.status_code == 200
        assert r.json() == []

    def test_returns_contract_for_mission(self):
        a = _make_approval(mission_id="m-list-mission")
        client.post(f"/approvals/{a.approval_id}/approve")
        r = client.get("/governance/contracts/mission/m-list-mission")
        assert r.status_code == 200
        assert len(r.json()) == 1


# ── GET /governance/contracts/{id} ───────────────────────────────────────────

class TestGovernanceGetContractEndpoint:

    def test_get_by_id(self):
        a = _make_approval()
        approve_resp = client.post(f"/approvals/{a.approval_id}/approve")
        gc_id = approve_resp.json()["governance_contract"]["contract_id"]
        r = client.get(f"/governance/contracts/{gc_id}")
        assert r.status_code == 200
        assert r.json()["contract_id"] == gc_id

    def test_404_for_missing(self):
        r = client.get("/governance/contracts/nonexistent-id")
        assert r.status_code == 404


# ── POST /governance/contracts/{id}/revoke ───────────────────────────────────

class TestGovernanceRevokeEndpoint:

    def test_revoke_active_contract(self):
        a = _make_approval()
        ar = client.post(f"/approvals/{a.approval_id}/approve")
        gc_id = ar.json()["governance_contract"]["contract_id"]
        r = client.post(f"/governance/contracts/{gc_id}/revoke",
                        json={"reason": "test revoke"})
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "REVOKED"

    def test_revoke_twice_409(self):
        a = _make_approval()
        ar = client.post(f"/approvals/{a.approval_id}/approve")
        gc_id = ar.json()["governance_contract"]["contract_id"]
        client.post(f"/governance/contracts/{gc_id}/revoke", json={"reason": "first"})
        r = client.post(f"/governance/contracts/{gc_id}/revoke", json={"reason": "second"})
        assert r.status_code == 409

    def test_revoke_missing_404(self):
        r = client.post("/governance/contracts/no-id/revoke", json={"reason": "x"})
        assert r.status_code == 404


# ── GET /governance/contracts/{id}/eligibility ───────────────────────────────

class TestGovernanceEligibilityEndpoint:

    def test_eligibility_active_contract(self):
        a = _make_approval()
        ar = client.post(f"/approvals/{a.approval_id}/approve")
        gc_id = ar.json()["governance_contract"]["contract_id"]
        r = client.get(f"/governance/contracts/{gc_id}/eligibility")
        assert r.status_code == 200
        data = r.json()
        assert "eligibility" in data
        assert "execution_authorization" in data

    def test_eligible_true_for_active(self):
        a = _make_approval()
        ar = client.post(f"/approvals/{a.approval_id}/approve")
        gc_id = ar.json()["governance_contract"]["contract_id"]
        r = client.get(f"/governance/contracts/{gc_id}/eligibility")
        assert r.json()["eligibility"]["eligible"] is True

    def test_authorized_true_for_active(self):
        a = _make_approval()
        ar = client.post(f"/approvals/{a.approval_id}/approve")
        gc_id = ar.json()["governance_contract"]["contract_id"]
        r = client.get(f"/governance/contracts/{gc_id}/eligibility")
        assert r.json()["execution_authorization"]["authorized"] is True

    def test_eligible_false_after_revoke(self):
        a = _make_approval()
        ar = client.post(f"/approvals/{a.approval_id}/approve")
        gc_id = ar.json()["governance_contract"]["contract_id"]
        client.post(f"/governance/contracts/{gc_id}/revoke", json={"reason": "compat"})
        r = client.get(f"/governance/contracts/{gc_id}/eligibility")
        assert r.json()["eligibility"]["eligible"] is False

    def test_404_for_missing(self):
        r = client.get("/governance/contracts/missing-id/eligibility")
        assert r.status_code == 404


# ── GET /governance/analytics ─────────────────────────────────────────────────

class TestGovernanceAnalyticsEndpoint:

    def test_analytics_200(self):
        r = client.get("/governance/analytics")
        assert r.status_code == 200

    def test_analytics_increments_on_approve(self):
        a = _make_approval()
        client.post(f"/approvals/{a.approval_id}/approve")
        r = client.get("/governance/analytics")
        assert r.json()["contracts_created"] >= 1


# ── GET /governance/inspect/{mission_id} ──────────────────────────────────────

class TestGovernanceInspectEndpoint:

    def test_inspect_200(self):
        r = client.get("/governance/inspect/m-inspect")
        assert r.status_code == 200

    def test_inspect_has_required_fields(self):
        r = client.get("/governance/inspect/m-inspect")
        data = r.json()
        for k in ["total_contracts", "active_count", "execution_eligible",
                  "analytics", "registry_stats", "latency_ms"]:
            assert k in data

    def test_inspect_shows_approved_contract(self):
        a = _make_approval(mission_id="m-insp-check")
        client.post(f"/approvals/{a.approval_id}/approve")
        r = client.get("/governance/inspect/m-insp-check")
        data = r.json()
        assert data["total_contracts"] == 1
        assert data["execution_eligible"] == 1
