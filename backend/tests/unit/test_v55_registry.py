"""
V5.5 Unit tests — MissionIntelligenceRegistry (16 tests).
"""
import time
import pytest

from app.mission.intelligence.registry import MissionIntelligenceRegistry
from app.mission.intelligence.models import (
    MissionIntelligenceReport, MissionAdvisoryState, MissionNextAction,
)
from datetime import datetime


def _report(mission_id="m1", readiness=0.80):
    return MissionIntelligenceReport(
        mission_id=mission_id,
        readiness_score=readiness,
        confidence=0.75,
        recommended_action="Open workflow",
        suggested_workflow="purchase_workflow",
        blockers=[],
        missing_information=[],
        reasoning="Test reasoning.",
        next_action=MissionNextAction(action="Open workflow", reasoning="Ready.", priority=1),
        advisory_state=MissionAdvisoryState.ready,
        workflow_recommendation=None,
        generated_at=datetime.utcnow(),
        latency_ms=5,
    )


class TestSetAndGet:
    def test_set_and_get_returns_report(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        r = _report("m1")
        reg.set("m1", r)
        cached = reg.get("m1")
        assert cached is not None
        assert cached.mission_id == "m1"

    def test_get_missing_returns_none(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        assert reg.get("nonexistent") is None

    def test_set_overwrites_previous(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        reg.set("m1", _report("m1", readiness=0.50))
        reg.set("m1", _report("m1", readiness=0.80))
        cached = reg.get("m1")
        assert cached.readiness_score == 0.80

    def test_separate_missions_stored_independently(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        reg.set("m1", _report("m1", readiness=0.50))
        reg.set("m2", _report("m2", readiness=0.90))
        assert reg.get("m1").readiness_score == 0.50
        assert reg.get("m2").readiness_score == 0.90


class TestTTLExpiry:
    def test_expired_entry_returns_none(self):
        reg = MissionIntelligenceRegistry(ttl=-1)  # always expired: delta >= 0 > -1
        reg.set("m1", _report())
        assert reg.get("m1") is None

    def test_fresh_entry_returned_within_ttl(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        reg.set("m1", _report())
        assert reg.get("m1") is not None


class TestInvalidate:
    def test_invalidate_removes_entry(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        reg.set("m1", _report())
        result = reg.invalidate("m1")
        assert result is True
        assert reg.get("m1") is None

    def test_invalidate_missing_returns_false(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        result = reg.invalidate("missing")
        assert result is False

    def test_invalidate_all_clears_all_entries(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        reg.set("m1", _report("m1"))
        reg.set("m2", _report("m2"))
        count = reg.invalidate_all()
        assert count == 2
        assert reg.get("m1") is None
        assert reg.get("m2") is None


class TestStats:
    def test_hits_and_misses_tracked(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        reg.get("missing")  # miss
        reg.set("m1", _report())
        reg.get("m1")  # hit
        reg.get("m1")  # hit
        s = reg.stats()
        assert s["cache_hits"] == 2
        assert s["cache_misses"] == 1

    def test_hit_rate_computed(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        reg.set("m1", _report())
        reg.get("m1")  # hit
        reg.get("m1")  # hit
        reg.get("missing")  # miss
        s = reg.stats()
        assert abs(s["hit_rate"] - 2/3) < 0.01

    def test_stats_zero_when_empty(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        s = reg.stats()
        assert s["cache_hits"] == 0
        assert s["cache_misses"] == 0
        assert s["hit_rate"] == 0.0


class TestResetForTesting:
    def test_reset_clears_cache_and_stats(self):
        reg = MissionIntelligenceRegistry(ttl=60)
        reg.set("m1", _report())
        reg.get("m1")
        reg._reset_for_testing()
        assert reg.get("m1") is None
        s = reg.stats()
        assert s["cache_hits"] == 0
        assert s["cache_misses"] == 1  # the get after reset counts as miss
