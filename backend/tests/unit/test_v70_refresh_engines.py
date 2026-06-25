"""
V7.0 Unit Tests — Refresh Engines + Recommendation Engine (22 tests).
"""
import pytest
import uuid

from app.browser.models import BrowserEventType, DecisionSignalType, make_event
from app.browser import analytics as bra
import app.browser.registry as ev_reg
from app.browser import timeline as tl
from app.tabs import registry as tab_reg
from app.mission.models import Mission
import app.mission.store as ms
from app.trust import analytics as trust_analytics
import app.trust.registry as trust_reg


@pytest.fixture(autouse=True)
def reset():
    bra._reset_for_testing()
    ev_reg._reset_for_testing()
    tl._reset_for_testing()
    tab_reg._reset_for_testing()
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()
    yield
    bra._reset_for_testing()
    ev_reg._reset_for_testing()
    tl._reset_for_testing()
    tab_reg._reset_for_testing()
    trust_analytics._reset_for_testing()
    trust_reg._reset_for_testing()


def _make_mission(title="Test"):
    m = Mission(mission_id=str(uuid.uuid4()), title=title, objective="test")
    ms.put(m)
    return m


# ── MissionRefreshEngine ──────────────────────────────────────────────────────

class TestMissionRefreshEngine:
    def test_refresh_returns_result(self):
        from app.browser.mission_refresh import MissionRefreshEngine
        engine = MissionRefreshEngine(cooldown_s=0)
        m = _make_mission()
        result = engine.refresh(m.mission_id, "test")
        assert result.mission_id == m.mission_id
        assert result.refreshed  is True

    def test_cooldown_skips_second_call(self):
        from app.browser.mission_refresh import MissionRefreshEngine
        engine = MissionRefreshEngine(cooldown_s=60)
        m = _make_mission()
        r1 = engine.refresh(m.mission_id)
        r2 = engine.refresh(m.mission_id)
        assert r1.refreshed  is True
        assert r2.refreshed  is False
        assert r2.skipped_reason == "cooldown"

    def test_reset_cooldown(self):
        from app.browser.mission_refresh import MissionRefreshEngine
        engine = MissionRefreshEngine(cooldown_s=60)
        m = _make_mission()
        engine.refresh(m.mission_id)
        engine.reset_cooldown(m.mission_id)
        r2 = engine.refresh(m.mission_id)
        assert r2.refreshed is True

    def test_result_has_latency(self):
        from app.browser.mission_refresh import MissionRefreshEngine
        engine = MissionRefreshEngine(cooldown_s=0)
        m = _make_mission()
        result = engine.refresh(m.mission_id)
        assert result.latency_ms >= 0

    def test_unknown_mission_still_returns_result(self):
        from app.browser.mission_refresh import MissionRefreshEngine
        engine = MissionRefreshEngine(cooldown_s=0)
        result = engine.refresh("nonexistent-mission-xyz")
        # Should not raise; just return what it can
        assert result.mission_id == "nonexistent-mission-xyz"

    def test_module_level_refresh(self):
        from app.browser.mission_refresh import refresh, _reset_for_testing
        _reset_for_testing()
        m = _make_mission()
        result = refresh(m.mission_id)
        assert result.mission_id == m.mission_id


# ── TrustRefreshEngine ────────────────────────────────────────────────────────

class TestTrustRefreshEngine:
    def test_refresh_invalidates_and_recomputes(self):
        from app.browser.trust_refresh import TrustRefreshEngine
        engine = TrustRefreshEngine()
        m = _make_mission()
        result = engine.refresh(m.mission_id)
        assert result.mission_id == m.mission_id
        assert result.refreshed  is True
        assert result.trust_score is not None
        assert 0.0 <= result.trust_score <= 1.0

    def test_risk_level_present(self):
        from app.browser.trust_refresh import TrustRefreshEngine
        engine = TrustRefreshEngine()
        m = _make_mission()
        result = engine.refresh(m.mission_id)
        assert result.risk_level in ("LOW", "MEDIUM", "HIGH", "CRITICAL")

    def test_tab_trust_score_present(self):
        from app.browser.trust_refresh import TrustRefreshEngine
        engine = TrustRefreshEngine()
        m = _make_mission()
        result = engine.refresh(m.mission_id)
        assert result.tab_trust_score is not None

    def test_module_level_refresh(self):
        from app.browser.trust_refresh import refresh
        m = _make_mission()
        result = refresh(m.mission_id)
        assert result.refreshed is True


# ── RecommendationRefreshEngine ───────────────────────────────────────────────

class TestRecommendationRefreshEngine:
    def test_returns_list(self):
        from app.browser.recommendation import refresh
        m = _make_mission()
        signals = refresh(m.mission_id)
        assert isinstance(signals, list)

    def test_signals_are_decision_signals(self):
        from app.browser.recommendation import refresh
        from app.browser.models import DecisionSignal
        m = _make_mission()
        signals = refresh(m.mission_id)
        for s in signals:
            assert isinstance(s, DecisionSignal)

    def test_signal_types_valid(self):
        from app.browser.recommendation import refresh
        m = _make_mission()
        signals = refresh(m.mission_id)
        valid = {DecisionSignalType.warning, DecisionSignalType.recommendation, DecisionSignalType.info}
        for s in signals:
            assert s.signal_type in valid

    def test_r1_high_trust_risk_generates_warning(self):
        from app.browser.recommendation import RecommendationRefreshEngine
        from app.trust.models import RiskLevel, TargetType, make_evaluation
        engine = RecommendationRefreshEngine()
        mock_trust = make_evaluation(TargetType.mission, "m1", 0.45, RiskLevel.high, True, 0.8, "High")
        signals = engine.refresh("m1", trust_ev=mock_trust)
        types = [s.signal_type for s in signals]
        assert DecisionSignalType.warning in types

    def test_r2_approval_required_generates_recommendation(self):
        from app.browser.recommendation import RecommendationRefreshEngine
        from app.trust.models import RiskLevel, TargetType, make_evaluation
        engine = RecommendationRefreshEngine()
        mock_trust = make_evaluation(TargetType.mission, "m1", 0.45, RiskLevel.high, True, 0.8, "")
        signals = engine.refresh("m1", trust_ev=mock_trust)
        types = [s.signal_type for s in signals]
        assert DecisionSignalType.recommendation in types

    def test_r3_missing_comparison_tab(self):
        from app.browser.recommendation import RecommendationRefreshEngine
        engine = RecommendationRefreshEngine()
        findings = [{"code": "MISSING_COMPARISON_TAB", "severity": "INFO"}]
        signals = engine.refresh("m1", tab_findings=findings)
        types = [s.signal_type for s in signals]
        assert DecisionSignalType.recommendation in types

    def test_r4_orphan_tabs_warning(self):
        from app.browser.recommendation import RecommendationRefreshEngine
        engine = RecommendationRefreshEngine()
        findings = [{"code": "ORPHAN_TABS", "severity": "INFO"}]
        signals = engine.refresh("m1", tab_findings=findings)
        types = [s.signal_type for s in signals]
        assert DecisionSignalType.warning in types

    def test_r7_stale_tabs_info(self):
        from app.browser.recommendation import RecommendationRefreshEngine
        engine = RecommendationRefreshEngine()
        findings = [{"code": "STALE_TABS", "severity": "INFO"}]
        signals = engine.refresh("m1", tab_findings=findings)
        types = [s.signal_type for s in signals]
        assert DecisionSignalType.info in types

    def test_no_signals_when_healthy(self):
        from app.browser.recommendation import RecommendationRefreshEngine
        from app.trust.models import RiskLevel, TargetType, make_evaluation
        engine = RecommendationRefreshEngine()
        healthy_trust = make_evaluation(TargetType.mission, "m1", 0.90, RiskLevel.low, False, 0.9, "")
        ctx = {"tab_count": 3, "tab_summaries": []}
        signals = engine.refresh("m1",
                                 trust_ev=healthy_trust,
                                 tab_ctx=ctx,
                                 tab_findings=[])
        warnings = [s for s in signals if s.signal_type == DecisionSignalType.warning]
        assert len(warnings) == 0
