"""
V8.0 Integration Tests — Human Approval Center REST API (44 tests).
"""
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.approvals import registry as reg
from app.approvals import analytics as anal
from app.approvals import timeline as tl
from app.approvals.models import (
    ApprovalStatus, ApprovalSourceType, ApprovalRiskLevel, make_approval_request,
)
from app.mission.models import Mission
import app.mission.store as ms
import app.trust.registry as trust_reg
from app.trust import analytics as trust_analytics
from app.decisions import registry as dec_reg
from app.decisions import analytics as dec_anal
from app.decisions import timeline as dec_tl

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset():
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()
    trust_reg._reset_for_testing()
    trust_analytics._reset_for_testing()
    dec_reg._reset_for_testing()
    dec_anal._reset_for_testing()
    dec_tl._reset_for_testing()
    yield
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()
    trust_reg._reset_for_testing()
    trust_analytics._reset_for_testing()
    dec_reg._reset_for_testing()
    dec_anal._reset_for_testing()
    dec_tl._reset_for_testing()


def _make_mission(title="Test") -> str:
    m = Mission(mission_id=str(uuid.uuid4()), title=title, objective="test")
    ms.put(m)
    return m.mission_id


def _add_approval(risk=ApprovalRiskLevel.medium, mission_id=None,
                  source_type=ApprovalSourceType.manual, status=None):
    r = make_approval_request(source_type, "src", "Test Approval", "Desc", risk,
                               mission_id=mission_id)
    reg.add(r)
    if status == "approved":
        reg.approve(r.approval_id)
    elif status == "rejected":
        reg.reject(r.approval_id, reason="test")
    return r


# ── GET /approvals ─────────────────────────────────────────────────────────────

class TestListApprovals:
    def test_list_200(self):
        r = client.get("/approvals")
        assert r.status_code == 200

    def test_list_returns_list(self):
        assert isinstance(client.get("/approvals").json(), list)

    def test_list_shows_added_approvals(self):
        _add_approval()
        _add_approval()
        assert len(client.get("/approvals").json()) >= 2

    def test_filter_by_status(self):
        _add_approval(status="approved")
        _add_approval()
        r = client.get("/approvals?status=APPROVED")
        assert r.status_code == 200
        items = r.json()
        assert all(d["status"] == "APPROVED" for d in items)

    def test_filter_by_mission(self):
        mid = _make_mission()
        _add_approval(mission_id=mid)
        _add_approval(mission_id="other")
        r = client.get(f"/approvals?mission_id={mid}")
        assert all(d["mission_id"] == mid for d in r.json())

    def test_invalid_status_400(self):
        assert client.get("/approvals?status=NONSENSE").status_code == 400

    def test_limit_respected(self):
        for _ in range(10):
            _add_approval()
        assert len(client.get("/approvals?limit=3").json()) <= 3

    def test_approval_schema_keys(self):
        _add_approval()
        d = client.get("/approvals").json()[0]
        for key in ("approval_id", "source_type", "title", "risk_level",
                    "status", "created_at", "expires_at"):
            assert key in d


# ── GET /approvals/pending ─────────────────────────────────────────────────────

class TestPendingApprovals:
    def test_pending_200(self):
        assert client.get("/approvals/pending").status_code == 200

    def test_pending_only_pending(self):
        _add_approval()
        _add_approval(status="approved")
        items = client.get("/approvals/pending").json()
        assert all(d["status"] == "PENDING" for d in items)

    def test_pending_includes_new(self):
        r = _add_approval()
        ids = [d["approval_id"] for d in client.get("/approvals/pending").json()]
        assert r.approval_id in ids


# ── GET /approvals/critical ────────────────────────────────────────────────────

class TestCriticalApprovals:
    def test_critical_200(self):
        assert client.get("/approvals/critical").status_code == 200

    def test_critical_only_high_and_critical(self):
        _add_approval(ApprovalRiskLevel.critical)
        _add_approval(ApprovalRiskLevel.low)
        items = client.get("/approvals/critical").json()
        assert all(d["risk_level"] in ("CRITICAL", "HIGH") for d in items)

    def test_critical_empty_when_none(self):
        _add_approval(ApprovalRiskLevel.low)
        assert client.get("/approvals/critical").json() == []


# ── GET /approvals/analytics ───────────────────────────────────────────────────

class TestApprovalAnalyticsEndpoint:
    def test_analytics_200(self):
        assert client.get("/approvals/analytics").status_code == 200

    def test_analytics_has_fields(self):
        body = client.get("/approvals/analytics").json()
        for f in ("created", "approved", "rejected", "expired",
                  "cancelled", "avg_approval_ms"):
            assert f in body

    def test_analytics_accumulate(self):
        anal.record_created("HIGH")
        anal.record_created("CRITICAL")
        body = client.get("/approvals/analytics").json()
        assert body["created"]  >= 2
        assert body["high"]     >= 1
        assert body["critical"] >= 1


# ── GET /approvals/inspect ─────────────────────────────────────────────────────

class TestApprovalInspectEndpoint:
    def test_inspect_200(self):
        assert client.get("/approvals/inspect").status_code == 200

    def test_inspect_keys(self):
        body = client.get("/approvals/inspect").json()
        for key in ("pending_count", "approved_count", "rejected_count",
                    "critical_pending", "analytics", "registry_stats", "latency_ms"):
            assert key in body

    def test_inspect_reflects_additions(self):
        _add_approval(ApprovalRiskLevel.critical)
        body = client.get("/approvals/inspect").json()
        assert body["pending_count"]   >= 1
        assert body["critical_pending"] >= 1


# ── GET /approvals/mission/{id} ───────────────────────────────────────────────

class TestMissionApprovals:
    def test_mission_200(self):
        mid = _make_mission()
        assert client.get(f"/approvals/mission/{mid}").status_code == 200

    def test_mission_filters_correctly(self):
        mid = _make_mission()
        _add_approval(mission_id=mid)
        _add_approval(mission_id="other")
        items = client.get(f"/approvals/mission/{mid}").json()
        assert all(d["mission_id"] == mid for d in items)

    def test_unknown_mission_returns_empty(self):
        assert client.get("/approvals/mission/unknown-m").json() == []


# ── POST /approvals/generate/{mission_id} ─────────────────────────────────────

class TestGenerateApprovals:
    def test_generate_existing_mission_200(self):
        mid = _make_mission()
        assert client.post(f"/approvals/generate/{mid}").status_code == 200

    def test_generate_response_schema(self):
        mid = _make_mission()
        body = client.post(f"/approvals/generate/{mid}").json()
        assert "mission_id"      in body
        assert "approvals_found" in body
        assert "approvals"       in body
        assert "latency_ms"      in body
        assert body["mission_id"] == mid

    def test_generate_unknown_mission_404(self):
        assert client.post("/approvals/generate/no-such-xyz").status_code == 404

    def test_generate_stores_in_registry(self):
        mid = _make_mission()
        body = client.post(f"/approvals/generate/{mid}").json()
        if body["approvals_found"] > 0:
            aid = body["approvals"][0]["approval_id"]
            assert reg.get(aid) is not None


# ── GET /approvals/{id} ───────────────────────────────────────────────────────

class TestGetApproval:
    def test_get_existing_200(self):
        r = _add_approval()
        resp = client.get(f"/approvals/{r.approval_id}")
        assert resp.status_code == 200
        assert resp.json()["approval_id"] == r.approval_id

    def test_get_unknown_404(self):
        assert client.get("/approvals/nonexistent-xyz").status_code == 404


# ── POST /approvals/{id}/approve ──────────────────────────────────────────────

class TestApproveEndpoint:
    def test_approve_200(self):
        r = _add_approval()
        resp = client.post(f"/approvals/{r.approval_id}/approve")
        assert resp.status_code == 200

    def test_approve_returns_status(self):
        r = _add_approval()
        body = client.post(f"/approvals/{r.approval_id}/approve").json()
        assert body["status"] == "APPROVED"

    def test_approve_updates_registry(self):
        r = _add_approval()
        client.post(f"/approvals/{r.approval_id}/approve")
        assert reg.get(r.approval_id).status == ApprovalStatus.approved

    def test_approve_returns_contract(self):
        r = _add_approval()
        body = client.post(f"/approvals/{r.approval_id}/approve").json()
        contract = body.get("contract")
        assert contract is not None
        assert contract["approved"] is True

    def test_approve_increments_analytics(self):
        anal._reset_for_testing()
        r = _add_approval()
        client.post(f"/approvals/{r.approval_id}/approve")
        assert anal.get_analytics()["approved"] == 1

    def test_approve_unknown_404(self):
        assert client.post("/approvals/nope/approve").status_code == 404

    def test_double_approve_409(self):
        r = _add_approval()
        client.post(f"/approvals/{r.approval_id}/approve")
        assert client.post(f"/approvals/{r.approval_id}/approve").status_code == 409


# ── POST /approvals/{id}/reject ───────────────────────────────────────────────

class TestRejectEndpoint:
    def test_reject_200(self):
        r = _add_approval()
        resp = client.post(f"/approvals/{r.approval_id}/reject",
                           json={"reason": "unsafe"})
        assert resp.status_code == 200

    def test_reject_returns_status(self):
        r = _add_approval()
        body = client.post(f"/approvals/{r.approval_id}/reject").json()
        assert body["status"] == "REJECTED"

    def test_reject_updates_registry(self):
        r = _add_approval()
        client.post(f"/approvals/{r.approval_id}/reject", json={"reason": "test"})
        updated = reg.get(r.approval_id)
        assert updated.status == ApprovalStatus.rejected
        assert updated.rejection_reason == "test"

    def test_reject_returns_contract(self):
        r = _add_approval()
        body = client.post(f"/approvals/{r.approval_id}/reject").json()
        assert body["contract"]["approved"] is False

    def test_reject_increments_analytics(self):
        anal._reset_for_testing()
        r = _add_approval()
        client.post(f"/approvals/{r.approval_id}/reject")
        assert anal.get_analytics()["rejected"] == 1

    def test_reject_unknown_404(self):
        assert client.post("/approvals/nope/reject").status_code == 404

    def test_reject_approved_409(self):
        r = _add_approval()
        client.post(f"/approvals/{r.approval_id}/approve")
        assert client.post(f"/approvals/{r.approval_id}/reject").status_code == 409


# ── POST /approvals/{id}/cancel ───────────────────────────────────────────────

class TestCancelEndpoint:
    def test_cancel_200(self):
        r = _add_approval()
        assert client.post(f"/approvals/{r.approval_id}/cancel").status_code == 200

    def test_cancel_updates_registry(self):
        r = _add_approval()
        client.post(f"/approvals/{r.approval_id}/cancel")
        assert reg.get(r.approval_id).status == ApprovalStatus.cancelled

    def test_cancel_unknown_404(self):
        assert client.post("/approvals/nope/cancel").status_code == 404

    def test_cancel_approved_409(self):
        r = _add_approval()
        client.post(f"/approvals/{r.approval_id}/approve")
        assert client.post(f"/approvals/{r.approval_id}/cancel").status_code == 409

    def test_cancel_increments_analytics(self):
        anal._reset_for_testing()
        r = _add_approval()
        client.post(f"/approvals/{r.approval_id}/cancel")
        assert anal.get_analytics()["cancelled"] == 1


# ── Mission inspect approvals integration (V8.0) ──────────────────────────────

class TestMissionInspectApprovals:
    def test_mission_inspect_has_approvals_field(self):
        mid = _make_mission()
        r = client.get(f"/mission/{mid}/inspect")
        assert r.status_code == 200
        assert "approvals" in r.json()

    def test_mission_inspect_approvals_structure(self):
        mid = _make_mission()
        _add_approval(mission_id=mid)
        body = client.get(f"/mission/{mid}/inspect").json()
        appr = body.get("approvals")
        if appr:
            assert "pending"  in appr
            assert "approved" in appr
            assert "rejected" in appr
            assert "critical" in appr
