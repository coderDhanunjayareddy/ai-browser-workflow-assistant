"""
V4.0 Unit Tests — ExecutionOpportunityDetector.

Tests cover:
  - Pure research queries → detected=False
  - Each action type keyword set
  - Workflow candidate flag
  - Required entities per action type
  - Missing information derivation
"""
import pytest
from app.intelligence.models import ActionType
from app.intelligence.opportunity_detector import ExecutionOpportunityDetector


@pytest.fixture
def det():
    return ExecutionOpportunityDetector()


# ── Pure research ─────────────────────────────────────────────────────────────

class TestPureResearch:
    def test_research_only_not_detected(self, det):
        opp = det.detect("research best flights from Hyderabad to Goa")
        assert opp.detected is False

    def test_research_confidence_zero(self, det):
        opp = det.detect("find info about Tesla")
        assert opp.confidence == 0.0

    def test_action_type_unknown_for_pure_research(self, det):
        opp = det.detect("look up climate change")
        assert opp.action_type == ActionType.unknown

    def test_workflow_candidate_false_for_research(self, det):
        opp = det.detect("learn about machine learning")
        assert opp.workflow_candidate is False

    def test_missing_information_empty_when_not_detected(self, det):
        opp = det.detect("tell me about Python")
        assert opp.detected is False


# ── Book / reservation ────────────────────────────────────────────────────────

class TestBookDetection:
    def test_book_keyword_detected(self, det):
        opp = det.detect("book a flight to Mumbai")
        assert opp.detected is True

    def test_book_action_type(self, det):
        opp = det.detect("book a hotel in Goa")
        assert opp.action_type == ActionType.book

    def test_reserve_keyword(self, det):
        opp = det.detect("reserve a table at the restaurant")
        assert opp.detected is True
        assert opp.action_type == ActionType.book

    def test_book_workflow_candidate(self, det):
        opp = det.detect("book tickets")
        assert opp.workflow_candidate is True

    def test_book_required_entities(self, det):
        opp = det.detect("book a flight")
        assert "destination" in opp.required_entities

    def test_book_confidence_high(self, det):
        opp = det.detect("book a flight to Delhi")
        assert opp.confidence == 0.9

    def test_ticket_keyword(self, det):
        opp = det.detect("get a train ticket to Chennai")
        assert opp.detected is True
        assert opp.action_type == ActionType.book


# ── Purchase ──────────────────────────────────────────────────────────────────

class TestPurchaseDetection:
    def test_buy_keyword(self, det):
        opp = det.detect("buy the iPhone 15")
        assert opp.detected is True
        assert opp.action_type == ActionType.purchase

    def test_order_keyword(self, det):
        opp = det.detect("order a pizza online")
        assert opp.detected is True
        assert opp.action_type == ActionType.purchase

    def test_purchase_keyword(self, det):
        opp = det.detect("I want to purchase this laptop")
        assert opp.detected is True
        assert opp.action_type == ActionType.purchase

    def test_purchase_required_entities(self, det):
        opp = det.detect("buy the product")
        assert "product_name" in opp.required_entities


# ── Register ──────────────────────────────────────────────────────────────────

class TestRegisterDetection:
    def test_sign_up(self, det):
        opp = det.detect("sign up for the newsletter")
        assert opp.detected is True
        assert opp.action_type == ActionType.register

    def test_subscribe(self, det):
        opp = det.detect("subscribe to the service")
        assert opp.detected is True
        assert opp.action_type == ActionType.register

    def test_register_required_entities(self, det):
        opp = det.detect("register for the course")
        assert "email" in opp.required_entities

    def test_enroll(self, det):
        opp = det.detect("enroll in the Python course")
        assert opp.action_type == ActionType.register


# ── Download ──────────────────────────────────────────────────────────────────

class TestDownloadDetection:
    def test_download_keyword(self, det):
        opp = det.detect("download Python 3.12")
        assert opp.detected is True
        assert opp.action_type == ActionType.download

    def test_install_keyword(self, det):
        opp = det.detect("install Visual Studio Code")
        assert opp.detected is True
        assert opp.action_type == ActionType.download


# ── Schedule ──────────────────────────────────────────────────────────────────

class TestScheduleDetection:
    def test_schedule_keyword(self, det):
        opp = det.detect("schedule an appointment with the doctor")
        assert opp.detected is True
        assert opp.action_type == ActionType.schedule

    def test_appointment_keyword(self, det):
        opp = det.detect("book an appointment tomorrow")
        assert opp.detected is True

    def test_schedule_required_entities(self, det):
        opp = det.detect("schedule a meeting")
        assert "date" in opp.required_entities


# ── Communicate ───────────────────────────────────────────────────────────────

class TestCommunicateDetection:
    def test_send_keyword(self, det):
        opp = det.detect("send an email to John")
        assert opp.detected is True
        assert opp.action_type == ActionType.communicate

    def test_message_keyword(self, det):
        opp = det.detect("message my friend on WhatsApp")
        assert opp.detected is True
        assert opp.action_type == ActionType.communicate


# ── Navigate ──────────────────────────────────────────────────────────────────

class TestNavigateDetection:
    def test_open_keyword(self, det):
        opp = det.detect("open the Amazon homepage")
        assert opp.detected is True
        assert opp.action_type == ActionType.navigate

    def test_navigate_not_workflow_candidate(self, det):
        opp = det.detect("go to Google")
        assert opp.action_type == ActionType.navigate
        assert opp.workflow_candidate is False


# ── Compound queries ──────────────────────────────────────────────────────────

class TestCompoundQueries:
    def test_research_and_book(self, det):
        opp = det.detect("research the best flight from Hyderabad to Goa and book it")
        assert opp.detected is True
        assert opp.action_type == ActionType.book

    def test_find_and_buy(self, det):
        opp = det.detect("find and buy cheapest laptop")
        assert opp.detected is True
        assert opp.action_type == ActionType.purchase

    def test_raw_keywords_populated(self, det):
        opp = det.detect("book a flight to Delhi")
        assert len(opp.raw_action_keywords) > 0
        assert "book" in opp.raw_action_keywords or "flight" in opp.raw_action_keywords
