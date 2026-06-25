"""
V4.0 Unit Tests — WorkflowReadinessAnalyzer.

Tests cover:
  - READY when all required entities present
  - BLOCKED when critical entity missing
  - PARTIALLY_READY when some (non-critical) entities missing
  - No requirements → READY
  - Readiness score calculation
"""
import pytest
from app.intelligence.models import ActionType, ExecutionOpportunity, ReadinessState
from app.intelligence.readiness_analyzer import WorkflowReadinessAnalyzer


def _make_opp(action_type: ActionType, required: list[str]) -> ExecutionOpportunity:
    return ExecutionOpportunity(
        detected=True,
        confidence=0.9,
        action_type=action_type,
        required_entities=required,
        missing_information=[],
        workflow_candidate=True,
        raw_action_keywords=[],
    )


class _FakeEntity:
    def __init__(self, name: str, aliases=None):
        self.name = name
        self.aliases = aliases or []
        self.metadata = {}


class _FakeSession:
    def __init__(self, entity_names: list[str]):
        self.active_entities = {
            name: _FakeEntity(name) for name in entity_names
        }
        self.active_goal = None


@pytest.fixture
def ana():
    return WorkflowReadinessAnalyzer()


class TestNoRequirements:
    def test_ready_with_no_requirements(self, ana):
        opp = _make_opp(ActionType.navigate, [])
        r = ana.analyze(opp, None, None)
        assert r.state == ReadinessState.ready

    def test_score_1_with_no_requirements(self, ana):
        opp = _make_opp(ActionType.navigate, [])
        r = ana.analyze(opp, None, None)
        assert r.readiness_score == 1.0


class TestReadyState:
    def test_ready_when_all_entities_present(self, ana):
        opp = _make_opp(ActionType.book, ["destination", "date"])
        session = _FakeSession(["destination", "date"])
        r = ana.analyze(opp, None, session)
        assert r.state == ReadinessState.ready

    def test_score_1_when_all_present(self, ana):
        opp = _make_opp(ActionType.book, ["destination", "date"])
        session = _FakeSession(["destination", "date"])
        r = ana.analyze(opp, None, session)
        assert r.readiness_score == 1.0

    def test_ready_entities_populated(self, ana):
        opp = _make_opp(ActionType.register, ["email"])
        session = _FakeSession(["email"])
        r = ana.analyze(opp, None, session)
        assert "email" in r.ready_entities

    def test_missing_entities_empty_when_ready(self, ana):
        opp = _make_opp(ActionType.register, ["email"])
        session = _FakeSession(["email"])
        r = ana.analyze(opp, None, session)
        assert r.missing_entities == []


class TestBlockedState:
    def test_blocked_when_critical_entity_missing(self, ana):
        opp = _make_opp(ActionType.book, ["origin", "destination", "date"])
        session = _FakeSession(["origin", "date"])  # destination missing
        r = ana.analyze(opp, None, session)
        assert r.state == ReadinessState.blocked

    def test_blocking_reason_present(self, ana):
        opp = _make_opp(ActionType.book, ["origin", "destination"])
        session = _FakeSession(["origin"])
        r = ana.analyze(opp, None, session)
        assert r.blocking_reason is not None
        assert len(r.blocking_reason) > 0

    def test_blocked_score_below_1(self, ana):
        opp = _make_opp(ActionType.book, ["origin", "destination", "date"])
        session = _FakeSession(["origin"])
        r = ana.analyze(opp, None, session)
        assert r.readiness_score < 1.0

    def test_blocked_when_no_session(self, ana):
        opp = _make_opp(ActionType.book, ["destination"])
        r = ana.analyze(opp, None, None)
        assert r.state == ReadinessState.blocked


class TestPartiallyReadyState:
    def test_partially_ready_when_non_critical_missing(self, ana):
        # For "book": critical is "destination". "origin" is required but not critical.
        opp = _make_opp(ActionType.book, ["origin", "destination", "date"])
        session = _FakeSession(["destination", "date"])  # "origin" missing (non-critical)
        r = ana.analyze(opp, None, session)
        # destination is present (critical met) but origin is missing → partially_ready
        assert r.state == ReadinessState.partially_ready

    def test_partially_ready_has_blocking_reason_none(self, ana):
        opp = _make_opp(ActionType.book, ["origin", "destination", "date"])
        session = _FakeSession(["destination", "date"])
        r = ana.analyze(opp, None, session)
        assert r.blocking_reason is None

    def test_score_between_0_and_1(self, ana):
        opp = _make_opp(ActionType.book, ["origin", "destination", "date"])
        session = _FakeSession(["destination"])
        r = ana.analyze(opp, None, session)
        assert 0.0 < r.readiness_score < 1.0


class TestScoreCalculation:
    def test_score_two_of_four(self, ana):
        opp = _make_opp(ActionType.schedule, ["date", "time", "location", "attendee"])
        session = _FakeSession(["date", "time"])
        r = ana.analyze(opp, None, session)
        assert r.readiness_score == 0.5
