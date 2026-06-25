"""
V5.5 Unit tests — WorkflowRecommendationEngine (16 tests).
"""
import pytest

from app.mission.intelligence import workflow_recommender
from app.mission.intelligence.workflow_recommender import recommend


class TestRecommendation:
    def test_book_intent_returns_booking_workflow(self):
        rec = recommend("Book flight to London", "", 0.80)
        assert rec is not None
        assert rec.workflow_type == "booking_workflow"

    def test_purchase_intent_returns_purchase_workflow(self):
        rec = recommend("Buy a laptop online", "", 0.70)
        assert rec is not None
        assert rec.workflow_type == "purchase_workflow"

    def test_register_intent_returns_registration_workflow(self):
        rec = recommend("Sign up for newsletter", "", 0.60)
        assert rec is not None
        assert rec.workflow_type == "registration_workflow"

    def test_schedule_intent_returns_scheduling_workflow(self):
        rec = recommend("Schedule dentist appointment", "", 0.75)
        assert rec is not None
        assert rec.workflow_type == "scheduling_workflow"

    def test_rent_intent_returns_rental_workflow(self):
        rec = recommend("Rent a car in London", "", 0.65)
        assert rec is not None
        assert rec.workflow_type == "rental_workflow"

    def test_apply_intent_returns_application_workflow(self):
        rec = recommend("Apply for software engineer position", "", 0.80)
        assert rec is not None
        assert rec.workflow_type == "application_workflow"

    def test_download_intent_returns_download_workflow(self):
        rec = recommend("Download the app", "", 0.60)
        assert rec is not None
        assert rec.workflow_type == "download_workflow"


class TestConfidence:
    def test_high_readiness_yields_high_confidence(self):
        rec = recommend("Book flight to Paris", "", 0.90)
        assert rec is not None
        assert rec.confidence >= 0.80

    def test_low_readiness_yields_lower_confidence(self):
        rec_high = recommend("Order laptop", "", 0.90)
        rec_low  = recommend("Order laptop", "", 0.30)
        assert rec_high is not None
        assert rec_low is not None
        assert rec_high.confidence > rec_low.confidence

    def test_confidence_never_exceeds_one(self):
        rec = recommend("Reserve hotel", "", 1.0)
        assert rec is not None
        assert rec.confidence <= 1.0

    def test_confidence_rounded_to_3_decimals(self):
        rec = recommend("Reserve a ticket", "", 0.75)
        assert rec is not None
        assert rec.confidence == round(rec.confidence, 3)


class TestActionType:
    def test_action_type_is_string_value(self):
        rec = recommend("Order a phone", "", 0.60)
        assert rec is not None
        assert isinstance(rec.action_type, str)
        assert rec.action_type == "purchase"

    def test_book_action_type_is_book(self):
        rec = recommend("Book flight", "", 0.60)
        assert rec is not None
        assert rec.action_type == "book"


class TestNoRecommendation:
    def test_empty_title_returns_none(self):
        rec = recommend("", "", 0.50)
        assert rec is None

    def test_unknown_intent_returns_none(self):
        # "research laptops" has no action keyword → unknown → None
        rec = recommend("research laptops best deals", "", 0.50)
        assert rec is None


class TestReasoning:
    def test_reasoning_is_non_empty_string(self):
        rec = recommend("Order laptop", "", 0.70)
        assert rec is not None
        assert isinstance(rec.reasoning, str)
        assert len(rec.reasoning) > 0
