"""
V8.0 Unit Tests — ApprovalRequest models (24 tests).
"""
import time
import pytest

from app.approvals.models import (
    ApprovalStatus, ApprovalSourceType, ApprovalRiskLevel, ApprovalRequest,
    ApprovalDecisionContract, RISK_ORDER, make_approval_request, DEFAULT_TTL_SECONDS,
)


class TestApprovalStatus:
    def test_five_statuses(self):
        assert len(list(ApprovalStatus)) == 5

    def test_pending_value(self):
        assert ApprovalStatus.pending.value == "PENDING"

    def test_approved_value(self):
        assert ApprovalStatus.approved.value == "APPROVED"

    def test_rejected_value(self):
        assert ApprovalStatus.rejected.value == "REJECTED"

    def test_expired_value(self):
        assert ApprovalStatus.expired.value == "EXPIRED"

    def test_cancelled_value(self):
        assert ApprovalStatus.cancelled.value == "CANCELLED"


class TestApprovalRiskLevel:
    def test_four_levels(self):
        assert len(list(ApprovalRiskLevel)) == 4

    def test_risk_order_critical_highest(self):
        assert RISK_ORDER[ApprovalRiskLevel.critical] > RISK_ORDER[ApprovalRiskLevel.high]
        assert RISK_ORDER[ApprovalRiskLevel.high]     > RISK_ORDER[ApprovalRiskLevel.medium]
        assert RISK_ORDER[ApprovalRiskLevel.medium]   > RISK_ORDER[ApprovalRiskLevel.low]


class TestApprovalSourceType:
    def test_four_source_types(self):
        assert len(list(ApprovalSourceType)) == 4

    def test_trust_engine_value(self):
        assert ApprovalSourceType.trust_engine.value == "TRUST_ENGINE"

    def test_decision_center_value(self):
        assert ApprovalSourceType.decision_center.value == "DECISION_CENTER"


class TestMakeApprovalRequest:
    def test_creates_approval_request(self):
        r = make_approval_request(
            ApprovalSourceType.trust_engine, "src-1",
            "Title", "Desc", ApprovalRiskLevel.high,
        )
        assert isinstance(r, ApprovalRequest)

    def test_generates_approval_id(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
        assert bool(r.approval_id)

    def test_default_status_pending(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
        assert r.status == ApprovalStatus.pending

    def test_expires_at_future(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
        assert r.expires_at > r.created_at

    def test_default_ttl(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
        assert abs((r.expires_at - r.created_at) - DEFAULT_TTL_SECONDS) < 1

    def test_mission_id_set(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D",
                                   ApprovalRiskLevel.low, mission_id="m1")
        assert r.mission_id == "m1"

    def test_is_pending_true_for_new(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
        assert r.is_pending is True

    def test_is_critical_true_for_high(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.high)
        assert r.is_critical is True

    def test_is_critical_true_for_critical(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.critical)
        assert r.is_critical is True

    def test_is_critical_false_for_low(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
        assert r.is_critical is False

    def test_to_dict_keys(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.medium)
        d = r.to_dict()
        for key in ("approval_id", "source_type", "source_id", "title", "description",
                    "risk_level", "priority", "created_at", "expires_at", "status"):
            assert key in d

    def test_to_dict_status_string(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
        assert r.to_dict()["status"] == "PENDING"

    def test_to_dict_risk_level_string(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.critical)
        assert r.to_dict()["risk_level"] == "CRITICAL"

    def test_is_expired_now_false_for_new(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
        assert r.is_expired_now is False

    def test_is_expired_now_true_when_past_expires(self):
        r = make_approval_request(ApprovalSourceType.manual, "s", "T", "D",
                                   ApprovalRiskLevel.low, ttl_seconds=0.001)
        time.sleep(0.01)
        assert r.is_expired_now is True

    def test_risk_order_property(self):
        r_crit = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.critical)
        r_low  = make_approval_request(ApprovalSourceType.manual, "s", "T", "D", ApprovalRiskLevel.low)
        assert r_crit.risk_order > r_low.risk_order


class TestApprovalDecisionContract:
    def test_creates_contract(self):
        c = ApprovalDecisionContract(
            approval_id     = "a1",
            approved        = True,
            approved_at     = time.time(),
            decision_source = "human_via_api",
        )
        assert c.approved is True

    def test_to_dict_keys(self):
        c = ApprovalDecisionContract(
            approval_id     = "a1",
            approved        = False,
            approved_at     = time.time(),
            decision_source = "human_via_api",
            mission_id      = "m1",
        )
        d = c.to_dict()
        for key in ("approval_id", "approved", "approved_at", "decision_source", "mission_id"):
            assert key in d

    def test_approved_false_for_rejection(self):
        c = ApprovalDecisionContract("a1", False, time.time(), "human_via_api")
        assert c.approved is False
