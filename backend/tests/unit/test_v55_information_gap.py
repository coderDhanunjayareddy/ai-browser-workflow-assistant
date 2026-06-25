"""
V5.5 Unit tests — MissionInformationGapAnalyzer (18 tests).
"""
import pytest

from app.mission.intelligence import information_gap
from app.mission.intelligence.models import GapCategory


def _ctx(title="Buy laptop online", task_summaries=None, entities=None, goals=None):
    from app.mission.context_registry import MissionContext
    from app.mission.models import MissionMemory
    from datetime import datetime

    summaries = task_summaries or []
    mem = MissionMemory(
        mission_id="m1",
        entities=entities or {},
        goals=goals or [],
        research_findings=[],
        execution_plans=[],
        decisions=[],
        last_updated=datetime.utcnow(),
    )
    return MissionContext(
        mission_id="m1",
        mission_title=title,
        mission_state="ACTIVE",
        priority=3,
        task_count=len(summaries),
        task_summaries=summaries,
        entities=entities or {},
        goals=goals or [],
        research_findings=[],
        execution_plans=[],
        approvals=[],
        memory=mem,
        latency_ms=0,
    )


class TestActionDetection:
    def test_purchase_intent_detects_product_name_gap(self):
        # "order laptop" → purchase action (avoids "macbook" which contains "book")
        ctx = _ctx("order laptop online", task_summaries=[])
        gaps = information_gap.analyze(ctx)
        field_names = [g.field_name for g in gaps]
        assert "product_name" in field_names

    def test_book_flight_detects_origin_destination_date_gaps(self):
        ctx = _ctx("book flight to New York", task_summaries=[])
        gaps = information_gap.analyze(ctx)
        field_names = [g.field_name for g in gaps]
        assert "destination" in field_names
        assert "date" in field_names

    def test_register_intent_detects_email_gap(self):
        ctx = _ctx("sign up for newsletter", task_summaries=[])
        gaps = information_gap.analyze(ctx)
        field_names = [g.field_name for g in gaps]
        assert "email" in field_names

    def test_schedule_intent_detects_date_and_time_gaps(self):
        ctx = _ctx("schedule dentist appointment", task_summaries=[])
        gaps = information_gap.analyze(ctx)
        field_names = [g.field_name for g in gaps]
        assert "date" in field_names
        assert "time" in field_names


class TestKnownEntitiesElimination:
    def test_known_entity_not_reported_as_gap(self):
        ctx = _ctx(
            "buy laptop",
            entities={"product_name": "MacBook Pro"},
            task_summaries=[],
        )
        gaps = information_gap.analyze(ctx)
        field_names = [g.field_name for g in gaps]
        assert "product_name" not in field_names

    def test_known_origin_not_reported(self):
        ctx = _ctx(
            "book flight",
            entities={"origin": "London Heathrow", "destination": "JFK", "date": "2026-07-01"},
            task_summaries=[],
        )
        gaps = information_gap.analyze(ctx)
        field_names = [g.field_name for g in gaps]
        assert "origin" not in field_names
        assert "destination" not in field_names
        assert "date" not in field_names


class TestGapCategories:
    def test_product_name_category_is_product(self):
        ctx = _ctx("buy headphones", task_summaries=[])
        gaps = information_gap.analyze(ctx)
        pn = next((g for g in gaps if g.field_name == "product_name"), None)
        assert pn is not None
        assert pn.category == GapCategory.product

    def test_date_category_is_temporal(self):
        ctx = _ctx("book flight to Paris", task_summaries=[])
        gaps = information_gap.analyze(ctx)
        d = next((g for g in gaps if g.field_name == "date"), None)
        assert d is not None
        assert d.category == GapCategory.temporal

    def test_email_category_is_identity(self):
        ctx = _ctx("register for event", task_summaries=[])
        gaps = information_gap.analyze(ctx)
        e = next((g for g in gaps if g.field_name == "email"), None)
        assert e is not None
        assert e.category == GapCategory.identity


class TestResearchGap:
    def test_no_research_adds_research_data_gap(self):
        ctx = _ctx("buy something", task_summaries=[
            {"task_id": "t1", "state": "CREATED", "query": "q", "goal": None,
             "has_research": False, "has_plan": False, "approval_count": 0}
        ])
        gaps = information_gap.analyze(ctx)
        field_names = [g.field_name for g in gaps]
        assert "research_data" in field_names

    def test_has_research_does_not_add_research_gap(self):
        ctx = _ctx("buy macbook", task_summaries=[
            {"task_id": "t1", "state": "COMPLETED", "query": "q", "goal": None,
             "has_research": True, "has_plan": False, "approval_count": 0}
        ])
        gaps = information_gap.analyze(ctx)
        field_names = [g.field_name for g in gaps]
        assert "research_data" not in field_names


class TestGapToDict:
    def test_gap_to_dict_has_all_fields(self):
        ctx = _ctx("book flight", task_summaries=[])
        gaps = information_gap.analyze(ctx)
        assert len(gaps) > 0
        d = gaps[0].to_dict()
        assert "field_name" in d
        assert "description" in d
        assert "category" in d

    def test_no_duplicate_field_names(self):
        ctx = _ctx("book flight to Paris", task_summaries=[])
        gaps = information_gap.analyze(ctx)
        names = [g.field_name for g in gaps]
        assert len(names) == len(set(names))


class TestNoGapsCase:
    def test_research_only_mission_with_all_entities_known(self):
        ctx = _ctx(
            "research laptops",  # no detectable book/buy action
            entities={"brand": "Apple"},
            task_summaries=[
                {"task_id": "t1", "state": "COMPLETED", "query": "q", "goal": None,
                 "has_research": True, "has_plan": False, "approval_count": 0}
            ],
        )
        gaps = information_gap.analyze(ctx)
        # "research laptops" → no known action type → no entity gaps (only maybe research_data)
        assert "product_name" not in [g.field_name for g in gaps]
