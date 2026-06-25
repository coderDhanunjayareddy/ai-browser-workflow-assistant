"""
V6.5 Unit Tests — TrustPolicyEngine (18 tests).
"""
import pytest
from app.trust.policy_engine import TrustPolicyEngine, evaluate
from app.trust.models import RiskLevel, TargetType


@pytest.fixture
def engine():
    return TrustPolicyEngine()


class TestBaseRiskMapping:
    def test_read_page_low_risk(self, engine):
        ev = engine.evaluate("read_page", readiness_score=0.8)
        assert ev.risk_level == RiskLevel.low

    def test_purchase_critical(self, engine):
        ev = engine.evaluate("purchase")
        assert ev.risk_level == RiskLevel.critical
        assert ev.approval_required is True

    def test_delete_critical(self, engine):
        ev = engine.evaluate("delete")
        assert ev.risk_level == RiskLevel.critical

    def test_form_fill_medium(self, engine):
        ev = engine.evaluate("form_fill")
        assert ev.risk_level == RiskLevel.medium

    def test_email_send_high(self, engine):
        ev = engine.evaluate("email_send")
        assert ev.risk_level == RiskLevel.high
        assert ev.approval_required is True


class TestTrustScore:
    def test_low_risk_high_score(self, engine):
        ev = engine.evaluate("read_page", readiness_score=1.0)
        assert ev.trust_score > 0.90

    def test_critical_risk_low_score(self, engine):
        ev = engine.evaluate("purchase", readiness_score=0.0)
        assert ev.trust_score < 0.30

    def test_blockers_reduce_score(self, engine):
        ev_no_blocker  = engine.evaluate("read_page", blocker_count=0)
        ev_with_blocker = engine.evaluate("read_page", blocker_count=3)
        assert ev_with_blocker.trust_score < ev_no_blocker.trust_score

    def test_missing_info_reduces_score(self, engine):
        ev_no_gap  = engine.evaluate("click", missing_info_count=0)
        ev_with_gap = engine.evaluate("click", missing_info_count=4)
        assert ev_with_gap.trust_score < ev_no_gap.trust_score

    def test_score_always_in_range(self, engine):
        for action in ["read_page", "click", "purchase", "delete", "xyz"]:
            ev = engine.evaluate(action, blocker_count=10, missing_info_count=10)
            assert 0.0 <= ev.trust_score <= 1.0


class TestRiskElevation:
    def test_workflow_type_purchase_elevates_to_critical(self, engine):
        ev = engine.evaluate("click", workflow_type="purchase_workflow")
        assert ev.risk_level == RiskLevel.critical

    def test_workflow_type_booking_elevates_risk(self, engine):
        ev = engine.evaluate("read_page", workflow_type="booking_workflow")
        assert ev.risk_level in (RiskLevel.medium, RiskLevel.high, RiskLevel.critical)

    def test_blockers_elevate_to_at_least_medium(self, engine):
        ev = engine.evaluate("read_page", blocker_count=2)
        assert ev.risk_level in (RiskLevel.medium, RiskLevel.high, RiskLevel.critical)

    def test_orphan_tab_role_elevates(self, engine):
        ev_normal = engine.evaluate("read_page", tab_role=None)
        ev_orphan  = engine.evaluate("read_page", tab_role="ORPHAN")
        assert ev_orphan.risk_level.value >= ev_normal.risk_level.value


class TestTargetType:
    def test_target_type_set(self, engine):
        ev = engine.evaluate("navigate", target_type=TargetType.mission, target_id="m1")
        assert ev.target_type == TargetType.mission
        assert ev.target_id   == "m1"

    def test_default_target_type_action(self, engine):
        ev = engine.evaluate("click")
        assert ev.target_type == TargetType.action


class TestConfidence:
    def test_confidence_in_range(self, engine):
        ev = engine.evaluate("purchase", readiness_score=0.9, blocker_count=0)
        assert 0.0 <= ev.confidence <= 1.0

    def test_high_readiness_higher_confidence(self, engine):
        lo = engine.evaluate("read_page", readiness_score=0.0)
        hi = engine.evaluate("read_page", readiness_score=1.0)
        assert hi.confidence >= lo.confidence


class TestReasoning:
    def test_reasoning_contains_action(self, engine):
        ev = engine.evaluate("purchase")
        assert "purchase" in ev.reasoning.lower()

    def test_reasoning_mentions_approval_when_required(self, engine):
        ev = engine.evaluate("delete")
        assert "approval" in ev.reasoning.lower()


class TestModuleLevel:
    def test_module_evaluate(self):
        ev = evaluate("read_page")
        assert ev.risk_level == RiskLevel.low
