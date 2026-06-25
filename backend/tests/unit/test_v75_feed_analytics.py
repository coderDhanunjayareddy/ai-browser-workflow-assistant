"""
V7.5 Unit Tests — DecisionFeed + DecisionAnalytics + DecisionTimeline (24 tests).
"""
import pytest

from app.decisions.models import (
    DecisionType, DecisionStatus, DecisionPriority, make_decision,
)
from app.decisions import registry as reg
from app.decisions import analytics as anal
from app.decisions import timeline as tl
from app.decisions import feed


@pytest.fixture(autouse=True)
def reset():
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()
    yield
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()


def _add(priority=DecisionPriority.medium, mission_id=None,
         dec_type=DecisionType.info):
    d = make_decision(dec_type, priority, "T", "D", "src", mission_id=mission_id)
    reg.add(d)
    return d


# ── DecisionFeed ──────────────────────────────────────────────────────────────

class TestDecisionFeed:
    def test_latest_returns_list(self):
        _add(); _add()
        assert len(feed.latest(limit=10)) >= 2

    def test_latest_newest_first(self):
        import time
        d1 = _add()
        time.sleep(0.01)
        d2 = _add()
        latest = feed.latest(limit=2)
        assert latest[0].decision_id == d2.decision_id

    def test_active_open_only(self):
        d1 = _add(mission_id="m1")
        d2 = _add(mission_id="m1")
        reg.update_status(d2.decision_id, DecisionStatus.resolved)
        active = feed.active("m1")
        ids = {d.decision_id for d in active}
        assert d1.decision_id in ids
        assert d2.decision_id not in ids

    def test_critical_only(self):
        _add(DecisionPriority.critical)
        _add(DecisionPriority.high)
        crit = feed.critical_only()
        assert all(d.priority == DecisionPriority.critical for d in crit)

    def test_for_mission(self):
        _add(mission_id="m-A")
        _add(mission_id="m-B")
        m_A = feed.for_mission("m-A")
        assert all(d.mission_id == "m-A" for d in m_A)

    def test_for_source(self):
        d = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "trust_engine")
        reg.add(d)
        items = feed.for_source("trust_engine")
        assert any(dd.decision_id == d.decision_id for dd in items)

    def test_summary_for_mission(self):
        _add(DecisionPriority.critical, mission_id="m1")
        _add(DecisionPriority.low,      mission_id="m1")
        s = feed.summary_for_mission("m1")
        assert "total_decisions"    in s
        assert "active_decisions"   in s
        assert "critical_decisions" in s
        assert "recent_decisions"   in s
        assert s["total_decisions"]    >= 2
        assert s["critical_decisions"] >= 1

    def test_summary_empty_mission(self):
        s = feed.summary_for_mission("nobody")
        assert s["total_decisions"]    == 0
        assert s["active_decisions"]   == 0
        assert s["critical_decisions"] == 0


# ── DecisionAnalytics ──────────────────────────────────────────────────────────

class TestDecisionAnalytics:
    def test_initial_zeros(self):
        a = anal.get_analytics()
        assert a["created"] == 0
        assert a["resolved"] == 0

    def test_record_created_medium(self):
        anal.record_created("MEDIUM")
        a = anal.get_analytics()
        assert a["created"] == 1
        assert a["medium"]  == 1

    def test_record_created_critical(self):
        anal.record_created("CRITICAL")
        a = anal.get_analytics()
        assert a["critical"] == 1

    def test_record_acknowledged(self):
        anal.record_acknowledged()
        a = anal.get_analytics()
        assert a["acknowledged"] == 1

    def test_record_dismissed(self):
        anal.record_dismissed()
        a = anal.get_analytics()
        assert a["dismissed"] == 1

    def test_record_resolved_with_duration(self):
        anal.record_resolved(duration_ms=500.0)
        a = anal.get_analytics()
        assert a["resolved"]           == 1
        assert a["avg_resolution_ms"]  == 500.0

    def test_avg_resolution_ms_multiple(self):
        anal.record_resolved(200.0)
        anal.record_resolved(400.0)
        a = anal.get_analytics()
        assert a["avg_resolution_ms"] == 300.0

    def test_reset_clears(self):
        anal.record_created("HIGH")
        anal._reset_for_testing()
        a = anal.get_analytics()
        assert a["created"] == 0


# ── DecisionTimeline ──────────────────────────────────────────────────────────

class TestDecisionTimeline:
    def test_record_and_get(self):
        tl.record("d1", "created", mission_id="m1", priority="HIGH",
                  title="Test", source="trust")
        events = tl.get("m1")
        assert len(events) == 1
        assert events[0]["decision_id"] == "d1"

    def test_newest_first(self):
        tl.record("d1", "created", mission_id="m1")
        tl.record("d2", "acknowledged", mission_id="m1")
        events = tl.get("m1")
        assert events[0]["decision_id"] == "d2"

    def test_summary(self):
        tl.record("d1", "created",      mission_id="m1")
        tl.record("d2", "acknowledged", mission_id="m1")
        s = tl.summary("m1")
        assert s["event_count"] == 2
        assert s["type_counts"].get("created",      0) == 1
        assert s["type_counts"].get("acknowledged", 0) == 1

    def test_recent_global(self):
        tl.record("d1", "created", mission_id="m1")
        tl.record("d2", "created", mission_id="m2")
        recent = tl.recent_global(limit=10)
        ids = {e["decision_id"] for e in recent}
        assert "d1" in ids and "d2" in ids

    def test_missions_with_decisions(self):
        tl.record("d1", "created", mission_id="m-alpha")
        assert "m-alpha" in tl.missions_with_decisions()

    def test_reset_clears(self):
        tl.record("d1", "created", mission_id="m1")
        tl._reset_for_testing()
        assert tl.get("m1") == []
