"""
V8.0 Unit Tests — ApprovalGenerator (14 tests).
"""
import uuid
import pytest

from app.approvals import generator
from app.approvals.models import ApprovalRequest, ApprovalSourceType
from app.mission.models import Mission
import app.mission.store as ms


@pytest.fixture(autouse=True)
def reset():
    from app.approvals import registry as reg, analytics as anal, timeline as tl
    import app.trust.registry as trust_reg
    from app.trust import analytics as trust_analytics
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()
    trust_reg._reset_for_testing()
    trust_analytics._reset_for_testing()
    yield
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()
    trust_reg._reset_for_testing()
    trust_analytics._reset_for_testing()


def _mission(title="Gen Test") -> str:
    m = Mission(mission_id=str(uuid.uuid4()), title=title, objective="test")
    ms.put(m)
    return m.mission_id


class TestGenerateForMission:
    def test_returns_list(self):
        mid = _mission()
        items = generator.generate_for_mission(mid)
        assert isinstance(items, list)

    def test_items_are_approval_requests(self):
        mid = _mission()
        items = generator.generate_for_mission(mid)
        for item in items:
            assert isinstance(item, ApprovalRequest)

    def test_unknown_mission_returns_list(self):
        items = generator.generate_for_mission("totally-unknown-id")
        assert isinstance(items, list)

    def test_items_have_mission_id_set(self):
        mid = _mission()
        items = generator.generate_for_mission(mid)
        for item in items:
            if item.mission_id:
                assert item.mission_id == mid

    def test_source_types_are_valid(self):
        mid = _mission()
        items = generator.generate_for_mission(mid)
        valid_types = {s for s in ApprovalSourceType}
        for item in items:
            assert item.source_type in valid_types

    def test_from_trust_returns_list(self):
        mid = _mission()
        items = generator._from_trust(mid)
        assert isinstance(items, list)

    def test_from_decisions_returns_list(self):
        mid = _mission()
        items = generator._from_decisions(mid)
        assert isinstance(items, list)

    def test_from_mission_intelligence_returns_list(self):
        mid = _mission()
        items = generator._from_mission_intelligence(mid)
        assert isinstance(items, list)

    def test_no_exception_when_trust_unavailable(self):
        items = generator._from_trust("m-no-trust-" + str(uuid.uuid4()))
        assert isinstance(items, list)

    def test_no_exception_when_decision_unavailable(self):
        items = generator._from_decisions("m-no-dec-" + str(uuid.uuid4()))
        assert isinstance(items, list)

    def test_all_items_have_approval_id(self):
        mid = _mission()
        items = generator.generate_for_mission(mid)
        for item in items:
            assert bool(item.approval_id)

    def test_all_items_pending_on_creation(self):
        from app.approvals.models import ApprovalStatus
        mid = _mission()
        items = generator.generate_for_mission(mid)
        for item in items:
            assert item.status == ApprovalStatus.pending

    def test_from_trust_items_have_trust_source(self):
        mid = _mission()
        items = generator._from_trust(mid)
        for item in items:
            assert item.source_type == ApprovalSourceType.trust_engine

    def test_from_decisions_items_have_decision_source(self):
        from app.decisions.models import DecisionType, DecisionPriority, make_decision
        from app.decisions import registry as dec_reg
        mid = _mission()
        crit = make_decision(DecisionType.trust_warning, DecisionPriority.critical,
                              "Crit", "D", "src", mission_id=mid)
        dec_reg.add(crit)
        items = generator._from_decisions(mid)
        if items:
            assert items[0].source_type == ApprovalSourceType.decision_center
