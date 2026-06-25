"""
V7.5 Unit Tests — Decision Models (24 tests).
"""
import pytest
from datetime import datetime

from app.decisions.models import (
    DecisionType, DecisionStatus, DecisionPriority,
    DecisionItem, make_decision, PRIORITY_ORDER,
)


class TestDecisionType:
    def test_five_types(self):
        assert len(list(DecisionType)) == 5

    def test_values(self):
        assert DecisionType.trust_warning.value  == "TRUST_WARNING"
        assert DecisionType.recommendation.value == "RECOMMENDATION"
        assert DecisionType.blocker.value        == "BLOCKER"
        assert DecisionType.opportunity.value    == "OPPORTUNITY"
        assert DecisionType.info.value           == "INFO"


class TestDecisionStatus:
    def test_four_statuses(self):
        assert len(list(DecisionStatus)) == 4

    def test_values(self):
        assert DecisionStatus.open.value         == "OPEN"
        assert DecisionStatus.acknowledged.value == "ACKNOWLEDGED"
        assert DecisionStatus.dismissed.value    == "DISMISSED"
        assert DecisionStatus.resolved.value     == "RESOLVED"


class TestDecisionPriority:
    def test_four_priorities(self):
        assert len(list(DecisionPriority)) == 4

    def test_values(self):
        assert DecisionPriority.low.value      == "LOW"
        assert DecisionPriority.medium.value   == "MEDIUM"
        assert DecisionPriority.high.value     == "HIGH"
        assert DecisionPriority.critical.value == "CRITICAL"

    def test_priority_order_dict(self):
        assert PRIORITY_ORDER[DecisionPriority.critical] > PRIORITY_ORDER[DecisionPriority.high]
        assert PRIORITY_ORDER[DecisionPriority.high]     > PRIORITY_ORDER[DecisionPriority.medium]
        assert PRIORITY_ORDER[DecisionPriority.medium]   > PRIORITY_ORDER[DecisionPriority.low]


class TestMakeDecision:
    def test_creates_decision_item(self):
        d = make_decision(DecisionType.blocker, DecisionPriority.high,
                          "Test", "Description", "test_src")
        assert isinstance(d, DecisionItem)

    def test_decision_id_generated(self):
        d = make_decision(DecisionType.info, DecisionPriority.low,
                          "T", "D", "src")
        assert isinstance(d.decision_id, str) and len(d.decision_id) > 0

    def test_default_status_open(self):
        d = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "src")
        assert d.status == DecisionStatus.open

    def test_mission_id_optional(self):
        d = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "src",
                          mission_id="m1")
        assert d.mission_id == "m1"

    def test_is_active_when_open(self):
        d = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "src")
        assert d.is_active is True

    def test_not_active_when_resolved(self):
        d = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "src")
        d.status = DecisionStatus.resolved
        assert d.is_active is False

    def test_priority_order_property(self):
        high = make_decision(DecisionType.blocker, DecisionPriority.high, "T", "D", "s")
        low  = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "s")
        assert high.priority_order > low.priority_order

    def test_to_dict_keys(self):
        d = make_decision(DecisionType.recommendation, DecisionPriority.medium,
                          "Title", "Desc", "src", mission_id="m1")
        dd = d.to_dict()
        for key in ("decision_id", "decision_type", "priority", "title",
                    "description", "source", "created_at", "status",
                    "mission_id", "task_id", "metadata"):
            assert key in dd

    def test_to_dict_values(self):
        d = make_decision(DecisionType.opportunity, DecisionPriority.low, "T", "D", "s")
        dd = d.to_dict()
        assert dd["decision_type"] == "OPPORTUNITY"
        assert dd["priority"]      == "LOW"
        assert dd["status"]        == "OPEN"

    def test_resolved_at_none_initially(self):
        d = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "s")
        assert d.resolved_at is None

    def test_created_at_is_datetime(self):
        d = make_decision(DecisionType.info, DecisionPriority.low, "T", "D", "s")
        assert isinstance(d.created_at, datetime)
