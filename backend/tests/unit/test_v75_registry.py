"""
V7.5 Unit Tests — DecisionRegistry (22 tests).
"""
import pytest

from app.decisions.models import (
    DecisionType, DecisionStatus, DecisionPriority, make_decision,
)
from app.decisions import registry as reg


@pytest.fixture(autouse=True)
def reset():
    reg._reset_for_testing()
    yield
    reg._reset_for_testing()


def _decision(priority=DecisionPriority.medium, mission_id=None,
              dec_type=DecisionType.info):
    return make_decision(dec_type, priority, "Test", "Desc", "src",
                         mission_id=mission_id)


class TestAddAndGet:
    def test_add_and_get(self):
        d = _decision()
        reg.add(d)
        out = reg.get(d.decision_id)
        assert out is not None
        assert out.decision_id == d.decision_id

    def test_get_unknown_returns_none(self):
        assert reg.get("nonexistent-id") is None

    def test_count_increases(self):
        reg.add(_decision())
        reg.add(_decision())
        assert reg.count() == 2

    def test_reset_clears(self):
        reg.add(_decision())
        reg._reset_for_testing()
        assert reg.count() == 0


class TestListAll:
    def test_list_all_returns_items(self):
        for _ in range(5):
            reg.add(_decision())
        assert len(reg.list_all()) == 5

    def test_list_all_limit(self):
        for _ in range(20):
            reg.add(_decision())
        assert len(reg.list_all(limit=5)) == 5

    def test_list_all_priority_sorted(self):
        reg.add(_decision(DecisionPriority.low))
        reg.add(_decision(DecisionPriority.critical))
        reg.add(_decision(DecisionPriority.medium))
        items = reg.list_all()
        assert items[0].priority == DecisionPriority.critical


class TestMissionIndex:
    def test_list_for_mission(self):
        d1 = _decision(mission_id="m1")
        d2 = _decision(mission_id="m1")
        d3 = _decision(mission_id="m2")
        reg.add(d1); reg.add(d2); reg.add(d3)
        items = reg.list_for_mission("m1")
        ids = {d.decision_id for d in items}
        assert d1.decision_id in ids
        assert d2.decision_id in ids
        assert d3.decision_id not in ids

    def test_list_for_mission_empty(self):
        assert reg.list_for_mission("nobody") == []


class TestUpdateStatus:
    def test_acknowledge(self):
        d = _decision()
        reg.add(d)
        ok = reg.update_status(d.decision_id, DecisionStatus.acknowledged)
        assert ok is True
        updated = reg.get(d.decision_id)
        assert updated.status == DecisionStatus.acknowledged
        assert updated.acknowledged_at is not None

    def test_resolve_sets_resolved_at(self):
        d = _decision()
        reg.add(d)
        reg.update_status(d.decision_id, DecisionStatus.resolved)
        updated = reg.get(d.decision_id)
        assert updated.resolved_at is not None

    def test_dismiss_sets_dismissed_at(self):
        d = _decision()
        reg.add(d)
        reg.update_status(d.decision_id, DecisionStatus.dismissed)
        updated = reg.get(d.decision_id)
        assert updated.dismissed_at is not None

    def test_update_unknown_returns_false(self):
        ok = reg.update_status("nope", DecisionStatus.resolved)
        assert ok is False


class TestListActive:
    def test_list_active_open_only(self):
        d1 = _decision(mission_id="m1")
        d2 = _decision(mission_id="m1")
        reg.add(d1); reg.add(d2)
        reg.update_status(d2.decision_id, DecisionStatus.resolved)
        active = reg.list_active(mission_id="m1")
        ids = {d.decision_id for d in active}
        assert d1.decision_id in ids
        assert d2.decision_id not in ids


class TestListCritical:
    def test_list_critical_only_critical(self):
        reg.add(_decision(DecisionPriority.critical))
        reg.add(_decision(DecisionPriority.high))
        reg.add(_decision(DecisionPriority.critical))
        critical = reg.list_critical()
        assert len(critical) == 2
        assert all(d.priority == DecisionPriority.critical for d in critical)


class TestStats:
    def test_stats_structure(self):
        reg.add(_decision())
        s = reg.stats()
        assert "cached_items"   in s
        assert "total_added"    in s
        assert "total_evicted"  in s
        assert "open_count"     in s
        assert s["total_added"] >= 1

    def test_open_count_decreases_after_resolve(self):
        d = _decision()
        reg.add(d)
        s1 = reg.stats()
        reg.update_status(d.decision_id, DecisionStatus.resolved)
        s2 = reg.stats()
        assert s2["open_count"] < s1["open_count"]
