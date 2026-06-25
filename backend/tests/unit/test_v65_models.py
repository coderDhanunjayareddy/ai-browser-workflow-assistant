"""
V6.5 Unit Tests — Trust Domain Models (20 tests).
"""
import pytest
from datetime import datetime

from app.trust.models import (
    RiskLevel, TargetType, TrustEvaluation, TrustDecisionContract,
    make_evaluation, max_risk, RISK_LEVEL_ORDER,
)


class TestRiskLevel:
    def test_four_values(self):
        assert len(RiskLevel) == 4

    def test_values_correct(self):
        assert RiskLevel.low.value      == "LOW"
        assert RiskLevel.medium.value   == "MEDIUM"
        assert RiskLevel.high.value     == "HIGH"
        assert RiskLevel.critical.value == "CRITICAL"

    def test_str_enum(self):
        assert RiskLevel.low == "LOW"

    def test_risk_level_order(self):
        assert RISK_LEVEL_ORDER[RiskLevel.low]      == 0
        assert RISK_LEVEL_ORDER[RiskLevel.critical] == 3

    def test_max_risk_higher_wins(self):
        assert max_risk(RiskLevel.low,      RiskLevel.critical) == RiskLevel.critical
        assert max_risk(RiskLevel.critical, RiskLevel.low)      == RiskLevel.critical
        assert max_risk(RiskLevel.medium,   RiskLevel.high)     == RiskLevel.high

    def test_max_risk_equal(self):
        assert max_risk(RiskLevel.medium, RiskLevel.medium) == RiskLevel.medium


class TestTargetType:
    def test_five_values(self):
        assert len(TargetType) == 5

    def test_values_correct(self):
        assert TargetType.mission.value  == "MISSION"
        assert TargetType.action.value   == "ACTION"
        assert TargetType.workflow.value == "WORKFLOW"
        assert TargetType.tab.value      == "TAB"
        assert TargetType.task.value     == "TASK"


class TestMakeEvaluation:
    def test_creates_evaluation(self):
        ev = make_evaluation(
            target_type       = TargetType.action,
            target_id         = "click",
            trust_score       = 0.75,
            risk_level        = RiskLevel.medium,
            approval_required = False,
            confidence        = 0.80,
            reasoning         = "Medium risk.",
        )
        assert isinstance(ev, TrustEvaluation)
        assert ev.target_type       == TargetType.action
        assert ev.trust_score       == 0.75
        assert ev.risk_level        == RiskLevel.medium
        assert ev.approval_required is False

    def test_score_clamped_above_1(self):
        ev = make_evaluation(TargetType.action, "x", 1.5, RiskLevel.low, False, 0.9, "")
        assert ev.trust_score == 1.0

    def test_score_clamped_below_0(self):
        ev = make_evaluation(TargetType.action, "x", -0.5, RiskLevel.critical, True, 0.9, "")
        assert ev.trust_score == 0.0

    def test_confidence_clamped(self):
        ev = make_evaluation(TargetType.action, "x", 0.5, RiskLevel.low, False, 2.0, "")
        assert ev.confidence == 1.0

    def test_evaluation_id_generated(self):
        ev = make_evaluation(TargetType.action, "x", 0.5, RiskLevel.low, False, 0.8, "")
        assert ev.evaluation_id is not None
        assert len(ev.evaluation_id) > 0

    def test_created_at_is_datetime(self):
        ev = make_evaluation(TargetType.action, "x", 0.5, RiskLevel.low, False, 0.8, "")
        assert isinstance(ev.created_at, datetime)

    def test_to_dict_complete(self):
        ev = make_evaluation(TargetType.action, "buy", 0.20, RiskLevel.critical, True, 0.9, "High risk")
        d = ev.to_dict()
        expected_keys = {"evaluation_id", "target_type", "target_id", "trust_score",
                         "risk_level", "approval_required", "confidence", "reasoning", "created_at"}
        assert expected_keys == set(d.keys())

    def test_to_dict_values(self):
        ev = make_evaluation(TargetType.mission, "m1", 0.80, RiskLevel.low, False, 0.90, "OK")
        d = ev.to_dict()
        assert d["target_type"]       == "MISSION"
        assert d["risk_level"]        == "LOW"
        assert d["approval_required"] is False
        assert d["trust_score"]       == 0.80


class TestTrustDecisionContract:
    def test_defaults_safe(self):
        c = TrustDecisionContract(
            contract_id="c1", evaluation_id="e1",
        )
        assert c.allowed_without_approval is False
        assert c.requires_user_approval   is True
        assert c.risk_level == RiskLevel.critical

    def test_to_dict(self):
        c = TrustDecisionContract(contract_id="c1", evaluation_id="e1")
        d = c.to_dict()
        assert "allowed_without_approval" in d
        assert d["allowed_without_approval"] is False
        assert d["requires_user_approval"]   is True
