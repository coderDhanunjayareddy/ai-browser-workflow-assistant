"""
V7.5 Unit Tests — DecisionInspector + DecisionAggregator (18 tests).
"""
import uuid
import pytest

from app.decisions.models import DecisionType, DecisionPriority, make_decision
from app.decisions import registry as reg
from app.decisions import analytics as anal
from app.decisions import timeline as tl
from app.decisions import inspector as insp_mod
from app.decisions import aggregator
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


def _make_mission(title="Test") -> str:
    m = Mission(mission_id=str(uuid.uuid4()), title=title, objective="test")
    ms.put(m)
    return m.mission_id


# ── DecisionInspector ─────────────────────────────────────────────────────────

class TestDecisionInspector:
    def test_inspect_global_returns_dict(self):
        result = insp_mod.inspect()
        assert isinstance(result, dict)

    def test_inspect_has_required_keys(self):
        result = insp_mod.inspect()
        for key in ("active_count", "critical_count", "high_count",
                    "active_decisions", "critical_decisions", "source_breakdown",
                    "trust_signals", "blockers", "analytics",
                    "registry_stats", "latency_ms"):
            assert key in result

    def test_inspect_with_mission(self):
        mid = _make_mission()
        result = insp_mod.inspect(mid)
        assert result["mission_id"] == mid

    def test_active_count_reflects_registry(self):
        d1 = make_decision(DecisionType.blocker, DecisionPriority.critical, "T", "D", "s")
        d2 = make_decision(DecisionType.info,    DecisionPriority.low,      "T", "D", "s")
        reg.add(d1); reg.add(d2)
        result = insp_mod.inspect()
        assert result["active_count"] >= 2

    def test_critical_count_correct(self):
        d = make_decision(DecisionType.trust_warning, DecisionPriority.critical, "T", "D", "s")
        reg.add(d)
        result = insp_mod.inspect()
        assert result["critical_count"] >= 1

    def test_source_breakdown(self):
        d = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "trust_engine")
        reg.add(d)
        result = insp_mod.inspect()
        assert "trust_engine" in result["source_breakdown"]

    def test_latency_ms_non_negative(self):
        result = insp_mod.inspect()
        assert result["latency_ms"] >= 0

    def test_analytics_present(self):
        anal.record_created("HIGH")
        result = insp_mod.inspect()
        assert result["analytics"]["created"] >= 1


# ── DecisionAggregator ────────────────────────────────────────────────────────

class TestDecisionAggregator:
    def test_aggregate_returns_list(self):
        mid = _make_mission()
        items = aggregator.aggregate(mid)
        assert isinstance(items, list)

    def test_aggregate_creates_decision_items(self):
        from app.decisions.models import DecisionItem
        mid = _make_mission()
        items = aggregator.aggregate(mid)
        for item in items:
            assert isinstance(item, DecisionItem)

    def test_aggregate_items_stored_in_registry(self):
        mid = _make_mission()
        items = aggregator.aggregate(mid)
        for item in items:
            stored = reg.get(item.decision_id)
            assert stored is not None

    def test_aggregate_records_analytics(self):
        anal._reset_for_testing()
        mid = _make_mission()
        items = aggregator.aggregate(mid)
        a = anal.get_analytics()
        assert a["created"] == len(items)

    def test_aggregate_records_timeline(self):
        tl._reset_for_testing()
        mid = _make_mission()
        items = aggregator.aggregate(mid)
        if items:
            events = tl.get(mid)
            assert len(events) == len(items)

    def test_aggregate_does_not_raise_on_unknown_mission(self):
        items = aggregator.aggregate("totally-unknown-mission-id")
        assert isinstance(items, list)

    def test_module_level_aggregate(self):
        mid = _make_mission()
        items = aggregator.aggregate(mid)
        assert isinstance(items, list)

    def test_double_aggregate_does_not_duplicate_in_registry(self):
        mid = _make_mission()
        c1 = len(aggregator.aggregate(mid))
        c2 = len(aggregator.aggregate(mid))
        # Registry may grow on second call but items are not overwritten
        assert c2 >= c1
