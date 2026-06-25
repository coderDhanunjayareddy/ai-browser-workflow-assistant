"""
V7.5 Unit Tests — PriorityEngine (18 tests).
"""
import pytest

from app.decisions.priority import PriorityEngine, classify, score
from app.decisions.models import DecisionPriority


class TestPriorityScore:
    def test_all_defaults_returns_low_score(self):
        engine = PriorityEngine()
        s = engine.score()
        assert s >= 0 and s < 30  # LOW threshold

    def test_critical_trust_risk_high_score(self):
        engine = PriorityEngine()
        s = engine.score(trust_risk_level="CRITICAL", confidence=1.0)
        assert s >= 40  # at least HIGH

    def test_high_trust_risk_medium_to_high(self):
        engine = PriorityEngine()
        s = engine.score(trust_risk_level="HIGH", confidence=1.0)
        assert s >= 30

    def test_blocker_adds_score(self):
        engine = PriorityEngine()
        s_no_blocker = engine.score(has_blocker=False, confidence=1.0)
        s_blocker    = engine.score(has_blocker=True,  confidence=1.0)
        assert s_blocker > s_no_blocker

    def test_low_readiness_adds_score(self):
        engine = PriorityEngine()
        s_good = engine.score(mission_readiness=0.9, confidence=1.0)
        s_bad  = engine.score(mission_readiness=0.2, confidence=1.0)
        assert s_bad > s_good

    def test_confidence_scales_score_down(self):
        engine = PriorityEngine()
        s_full = engine.score(trust_risk_level="HIGH", confidence=1.0)
        s_low  = engine.score(trust_risk_level="HIGH", confidence=0.1)
        assert s_low < s_full

    def test_trust_warning_type_boost(self):
        engine = PriorityEngine()
        s_warn = engine.score(decision_type="TRUST_WARNING", confidence=1.0)
        s_info = engine.score(decision_type="INFO",          confidence=1.0)
        assert s_warn > s_info

    def test_score_capped_at_100(self):
        engine = PriorityEngine()
        s = engine.score(
            trust_risk_level="CRITICAL",
            has_blocker=True,
            mission_readiness=0.1,
            confidence=1.0,
            decision_type="BLOCKER",
        )
        assert s <= 100


class TestPriorityClassify:
    def test_critical_trust_risk_critical_priority(self):
        engine = PriorityEngine()
        p = engine.classify(
            trust_risk_level  = "CRITICAL",
            has_blocker       = True,
            mission_readiness = 0.2,
            confidence        = 1.0,
            decision_type     = "TRUST_WARNING",
        )
        assert p == DecisionPriority.critical

    def test_high_risk_blocker_high_or_critical(self):
        engine = PriorityEngine()
        p = engine.classify(trust_risk_level="HIGH", has_blocker=True, confidence=1.0)
        assert p in (DecisionPriority.high, DecisionPriority.critical)

    def test_defaults_low(self):
        engine = PriorityEngine()
        p = engine.classify()
        assert p == DecisionPriority.low

    def test_medium_trust_no_blocker_low_or_medium(self):
        engine = PriorityEngine()
        p = engine.classify(trust_risk_level="MEDIUM", confidence=0.5)
        assert p in (DecisionPriority.low, DecisionPriority.medium)

    def test_module_level_classify(self):
        p = classify()
        assert isinstance(p, DecisionPriority)

    def test_module_level_score(self):
        s = score()
        assert isinstance(s, int)
        assert 0 <= s <= 100


class TestPriorityFromScore:
    def test_score_90_critical(self):
        engine = PriorityEngine()
        assert engine.priority_from_score(90) == DecisionPriority.critical

    def test_score_60_high(self):
        engine = PriorityEngine()
        assert engine.priority_from_score(60) == DecisionPriority.high

    def test_score_30_medium(self):
        engine = PriorityEngine()
        assert engine.priority_from_score(30) == DecisionPriority.medium

    def test_score_0_low(self):
        engine = PriorityEngine()
        assert engine.priority_from_score(0) == DecisionPriority.low
