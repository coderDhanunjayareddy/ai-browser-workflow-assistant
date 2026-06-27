"""
V8.0 Unit Tests — ApprovalInspector (18 tests).
"""
import uuid
import pytest

from app.approvals import inspector as insp
from app.approvals import registry as reg
from app.approvals import analytics as anal
from app.approvals import timeline as tl
from app.approvals.models import (
    ApprovalSourceType, ApprovalRiskLevel, ApprovalStatus, make_approval_request,
)
from app.mission.models import Mission
import app.mission.store as ms


@pytest.fixture(autouse=True)
def reset():
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()
    yield
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()


def _mission() -> str:
    m = Mission(mission_id=str(uuid.uuid4()), title="Insp Test", objective="test")
    ms.put(m)
    return m.mission_id


def _add(risk=ApprovalRiskLevel.high, mission_id=None):
    r = make_approval_request(ApprovalSourceType.trust_engine, "src", "T", "D", risk,
                               mission_id=mission_id)
    reg.add(r)
    return r


class TestApprovalInspector:
    def test_global_inspect_returns_dict(self):
        result = insp.inspect()
        assert isinstance(result, dict)

    def test_required_keys_present(self):
        result = insp.inspect()
        for key in ("mission_id", "pending_count", "approved_count", "rejected_count",
                    "critical_pending", "pending_approvals", "critical_approvals",
                    "source_breakdown", "analytics", "registry_stats",
                    "trust_signals", "decision_context", "mission_context",
                    "timeline_summary", "latency_ms"):
            assert key in result

    def test_global_mission_id_none(self):
        assert insp.inspect()["mission_id"] is None

    def test_mission_inspect_sets_mission_id(self):
        mid = _mission()
        result = insp.inspect(mid)
        assert result["mission_id"] == mid

    def test_pending_count_reflects_registry(self):
        _add()
        _add()
        result = insp.inspect()
        assert result["pending_count"] >= 2

    def test_critical_pending_count(self):
        _add(ApprovalRiskLevel.critical)
        result = insp.inspect()
        assert result["critical_pending"] >= 1

    def test_source_breakdown_populated(self):
        _add(ApprovalRiskLevel.high)
        result = insp.inspect()
        assert "TRUST_ENGINE" in result["source_breakdown"]

    def test_analytics_present_in_result(self):
        anal.record_created("HIGH")
        result = insp.inspect()
        assert result["analytics"]["created"] >= 1

    def test_registry_stats_present(self):
        result = insp.inspect()
        assert "cached_items" in result["registry_stats"]

    def test_approved_count_updates(self):
        r = _add()
        reg.approve(r.approval_id)
        result = insp.inspect()
        assert result["approved_count"] >= 1

    def test_rejected_count_updates(self):
        r = _add()
        reg.reject(r.approval_id)
        result = insp.inspect()
        assert result["rejected_count"] >= 1

    def test_latency_ms_non_negative(self):
        result = insp.inspect()
        assert result["latency_ms"] >= 0

    def test_pending_approvals_is_list(self):
        result = insp.inspect()
        assert isinstance(result["pending_approvals"], list)

    def test_critical_approvals_is_list(self):
        result = insp.inspect()
        assert isinstance(result["critical_approvals"], list)

    def test_mission_context_populated_for_known_mission(self):
        mid = _mission()
        result = insp.inspect(mid)
        assert result["mission_context"] is not None
        assert result["mission_context"]["mission_id"] == mid

    def test_trust_signals_non_crashing_for_unknown(self):
        result = insp.inspect("totally-unknown-mission-xyz")
        assert isinstance(result, dict)

    def test_no_exception_on_empty_registry(self):
        result = insp.inspect()
        assert result["pending_count"] == 0

    def test_pending_approvals_list_structure(self):
        _add()
        result = insp.inspect()
        if result["pending_approvals"]:
            item = result["pending_approvals"][0]
            assert "approval_id" in item
            assert "status" in item
