"""
V6.5 Unit Tests — TrustAnalytics + TrustRegistry + ApprovalAdvisorV2 (25 tests).
"""
import time
import pytest

from app.trust.models import RiskLevel, TargetType, make_evaluation
from app.trust import analytics as trust_analytics
import app.trust.registry as trust_reg
from app.trust.approval_advisor import ApprovalAdvisorV2, requires_approval, reasoning


@pytest.fixture(autouse=True)
def reset():
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()
    yield
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()


def _ev(risk=RiskLevel.low, approval=False, score=0.9):
    return make_evaluation(TargetType.action, "x", score, risk, approval, 0.9, "ok")


# ── ApprovalAdvisorV2 ─────────────────────────────────────────────────────────

class TestApprovalAdvisorV2:
    def test_low_never_requires(self):
        adv = ApprovalAdvisorV2()
        assert adv.requires_approval(RiskLevel.low) is False

    def test_medium_default_false(self):
        adv = ApprovalAdvisorV2()
        assert adv.requires_approval(RiskLevel.medium) is False

    def test_medium_configurable_true(self):
        adv = ApprovalAdvisorV2(medium_requires=True)
        assert adv.requires_approval(RiskLevel.medium) is True

    def test_high_always_requires(self):
        adv = ApprovalAdvisorV2()
        assert adv.requires_approval(RiskLevel.high) is True

    def test_critical_always_requires(self):
        adv = ApprovalAdvisorV2()
        assert adv.requires_approval(RiskLevel.critical) is True

    def test_reasoning_low_permissive(self):
        adv = ApprovalAdvisorV2()
        r = adv.reasoning(RiskLevel.low)
        assert "approval" in r.lower() or "low" in r.lower()

    def test_reasoning_critical_mentions_approval(self):
        adv = ApprovalAdvisorV2()
        r = adv.reasoning(RiskLevel.critical)
        assert "approval" in r.lower()

    def test_module_requires_approval(self):
        assert requires_approval(RiskLevel.critical) is True
        assert requires_approval(RiskLevel.low)      is False

    def test_module_reasoning(self):
        r = reasoning(RiskLevel.high)
        assert isinstance(r, str)
        assert len(r) > 0


# ── TrustAnalytics ────────────────────────────────────────────────────────────

class TestTrustAnalytics:
    def test_initial_state_zeros(self):
        a = trust_analytics.get_analytics()
        assert a["trust_evaluations"] == 0
        assert a["approval_required"] == 0
        assert a["avg_trust_score"]   == 0.0

    def test_record_low(self):
        trust_analytics.record_evaluation(RiskLevel.low, False)
        a = trust_analytics.get_analytics()
        assert a["trust_evaluations"] == 1
        assert a["low_risk"]          == 1
        assert a["medium_risk"]       == 0

    def test_record_critical(self):
        trust_analytics.record_evaluation(RiskLevel.critical, True)
        a = trust_analytics.get_analytics()
        assert a["critical_risk"]    == 1
        assert a["approval_required"] == 1

    def test_multi_bucket_counts(self):
        trust_analytics.record_evaluation(RiskLevel.low,      False)
        trust_analytics.record_evaluation(RiskLevel.medium,   False)
        trust_analytics.record_evaluation(RiskLevel.high,     True)
        trust_analytics.record_evaluation(RiskLevel.critical, True)
        a = trust_analytics.get_analytics()
        assert a["trust_evaluations"]      == 4
        assert a["low_risk"]               == 1
        assert a["medium_risk"]            == 1
        assert a["high_risk"]              == 1
        assert a["critical_risk"]          == 1
        assert a["approval_required"]      == 2

    def test_average_trust_score(self):
        trust_analytics.record_trust_score(0.8)
        trust_analytics.record_trust_score(0.6)
        a = trust_analytics.get_analytics()
        assert abs(a["avg_trust_score"] - 0.70) < 0.01

    def test_reset_clears(self):
        trust_analytics.record_evaluation(RiskLevel.critical, True)
        trust_analytics._reset_for_testing()
        a = trust_analytics.get_analytics()
        assert a["trust_evaluations"] == 0

    def test_approval_recommended_field(self):
        trust_analytics.record_evaluation(RiskLevel.high, True)
        a = trust_analytics.get_analytics()
        assert a["approval_recommended"] >= 0


# ── TrustRegistry ─────────────────────────────────────────────────────────────

class TestTrustRegistry:
    def test_miss_returns_none(self):
        assert trust_reg.get(TargetType.action, "unknown") is None

    def test_set_and_get(self):
        ev = _ev()
        trust_reg.set_evaluation(ev)
        out = trust_reg.get(TargetType.action, "x")
        assert out is not None
        assert out.trust_score == ev.trust_score

    def test_overwrite(self):
        ev1 = _ev(score=0.80)
        ev2 = _ev(score=0.50)
        trust_reg.set_evaluation(ev1)
        trust_reg.set_evaluation(ev2)
        out = trust_reg.get(TargetType.action, "x")
        assert out.trust_score == 0.50

    def test_invalidate(self):
        ev = _ev()
        trust_reg.set_evaluation(ev)
        trust_reg.invalidate(TargetType.action, "x")
        assert trust_reg.get(TargetType.action, "x") is None

    def test_invalidate_all(self):
        ev1 = _ev(score=0.8)
        ev2 = make_evaluation(TargetType.mission, "m1", 0.7, RiskLevel.medium, False, 0.9, "ok")
        trust_reg.set_evaluation(ev1)
        trust_reg.set_evaluation(ev2)
        trust_reg.invalidate_all()
        assert trust_reg.get(TargetType.action,  "x")  is None
        assert trust_reg.get(TargetType.mission, "m1") is None

    def test_stats_structure(self):
        st = trust_reg.stats()
        assert "cache_size"  in st
        assert "cache_hits"  in st
        assert "cache_misses" in st

    def test_ttl_expiry(self):
        import app.trust.registry as reg_module
        original_ttl = reg_module._registry._ttl
        reg_module._registry._ttl = 0
        try:
            ev = _ev()
            trust_reg.set_evaluation(ev)
            time.sleep(0.01)
            out = trust_reg.get(TargetType.action, "x")
            assert out is None
        finally:
            reg_module._registry._ttl = original_ttl

    def test_different_target_types_isolated(self):
        ev_action  = make_evaluation(TargetType.action,  "buy", 0.5, RiskLevel.critical, True,  0.9, "a")
        ev_mission = make_evaluation(TargetType.mission, "buy", 0.9, RiskLevel.low,      False, 0.9, "m")
        trust_reg.set_evaluation(ev_action)
        trust_reg.set_evaluation(ev_mission)
        assert trust_reg.get(TargetType.action,  "buy").trust_score == 0.5
        assert trust_reg.get(TargetType.mission, "buy").trust_score == 0.9
