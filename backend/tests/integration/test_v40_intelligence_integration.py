"""
V4.0 Integration Tests — Intelligence Engine end-to-end.

Tests cover:
  1. Research-only flow (no execution opportunity)
  2. Research + workflow flow (opportunity detected, plan built)
  3. Missing information flow (BLOCKED state)
  4. Approval classification (SAFE / REQUIRES_APPROVAL / HIGH_RISK)
  5. Workflow preparation (bootstrap facts generated)
  6. Analytics tracking
  7. AmbientAssistant integration (mocked research engine)
"""
import uuid
from unittest.mock import patch, MagicMock
import pytest

from app.intelligence import analytics as intel_analytics
from app.intelligence.engine import run_intelligence
from app.intelligence.models import ReadinessState, ApprovalLevel, ActionType


def setup_function():
    intel_analytics._reset_for_testing()


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeEntity:
    def __init__(self, name, value=None):
        self.name = name
        self.aliases = []
        self.metadata = {"value": value or name}


class _FakeSession:
    def __init__(self, entity_names=None, goal_text=None):
        self.active_entities = {n: _FakeEntity(n) for n in (entity_names or [])}
        self.active_goal = None
        if goal_text:
            self.active_goal = type("G", (), {"goal_text": goal_text, "status": type("S", (), {"value": "active"})()})()


# ── 1. Research-only flow ─────────────────────────────────────────────────────

class TestResearchOnlyFlow:
    def test_pure_research_not_detected(self):
        result = run_intelligence(
            query="research the best flights from Hyderabad to Goa",
            topic="flights from Hyderabad to Goa",
            research_summary="Various flight options available.",
        )
        assert result.opportunity.detected is False

    def test_pure_research_no_plan(self):
        result = run_intelligence(
            query="find info about electric cars",
            topic="electric cars",
            research_summary="Electric cars are efficient.",
        )
        assert result.execution_plan is None

    def test_pure_research_no_recommendations(self):
        result = run_intelligence(
            query="look into quantum computing",
            topic="quantum computing",
            research_summary="QC uses qubits.",
        )
        assert result.recommendations == []

    def test_pure_research_no_bootstrap(self):
        result = run_intelligence(
            query="learn about machine learning",
            topic="machine learning",
            research_summary="ML is a subset of AI.",
        )
        assert result.bootstrap_facts is None

    def test_pure_research_no_goal_tree(self):
        result = run_intelligence(
            query="research Python frameworks",
            topic="Python frameworks",
            research_summary="",
        )
        assert result.goal_tree is None

    def test_pure_research_analytics_recorded(self):
        intel_analytics._reset_for_testing()
        run_intelligence("research flights", "flights", "")
        data = intel_analytics.get_analytics()
        assert data["research_only_count"] == 1
        assert data["opportunities_detected"] == 0


# ── 2. Research + workflow flow ───────────────────────────────────────────────

class TestResearchAndWorkflowFlow:
    def test_book_opportunity_detected(self):
        result = run_intelligence(
            query="research and book cheapest flight to Mumbai",
            topic="flight to Mumbai",
            research_summary="Flights available from ₹3,000.",
        )
        assert result.opportunity.detected is True
        assert result.opportunity.action_type == ActionType.book

    def test_plan_generated(self):
        result = run_intelligence(
            query="book a hotel in Goa",
            topic="hotel in Goa",
            research_summary="Hotels available.",
        )
        assert result.execution_plan is not None

    def test_workflow_type_booking(self):
        result = run_intelligence(
            query="book a flight to Delhi",
            topic="flight to Delhi",
            research_summary="",
        )
        assert result.execution_plan.workflow_type == "booking_workflow"

    def test_goal_tree_generated(self):
        result = run_intelligence(
            query="book a flight to Chennai",
            topic="flight to Chennai",
            research_summary="",
        )
        assert result.goal_tree is not None
        assert result.goal_tree.root_id in result.goal_tree.nodes

    def test_recommendations_generated(self):
        result = run_intelligence(
            query="find and book cheapest flight to Hyderabad",
            topic="flight to Hyderabad",
            research_summary="",
        )
        assert len(result.recommendations) >= 1

    def test_bootstrap_facts_generated(self):
        result = run_intelligence(
            query="book a hotel in Mumbai",
            topic="hotel in Mumbai",
            research_summary="Executive summary here.",
        )
        assert result.bootstrap_facts is not None
        assert result.bootstrap_facts.workflow_type == "booking_workflow"

    def test_analytics_opportunity_counted(self):
        intel_analytics._reset_for_testing()
        run_intelligence("book a flight to Goa", "flight to Goa", "")
        data = intel_analytics.get_analytics()
        assert data["opportunities_detected"] == 1

    def test_analytics_plan_counted(self):
        intel_analytics._reset_for_testing()
        run_intelligence("buy a laptop", "laptop", "")
        data = intel_analytics.get_analytics()
        assert data["plans_built"] == 1


# ── 3. Missing information flow ───────────────────────────────────────────────

class TestMissingInformationFlow:
    def test_blocked_when_destination_missing(self):
        # No cognitive session → no entities → destination missing → BLOCKED
        result = run_intelligence(
            query="book a flight",
            topic="flight",
            research_summary="",
        )
        assert result.readiness is not None
        assert result.readiness.state == ReadinessState.blocked

    def test_blocking_reason_present(self):
        result = run_intelligence("book a flight", "flight", "")
        assert result.readiness.blocking_reason is not None

    def test_missing_entities_listed(self):
        result = run_intelligence("book a flight", "flight", "")
        assert len(result.readiness.missing_entities) > 0

    def test_readiness_score_zero_when_all_missing(self):
        result = run_intelligence("book a flight", "flight", "")
        assert result.readiness.readiness_score == 0.0

    def test_partially_ready_with_session(self):
        session = _FakeSession(["destination"])  # has destination but not origin or date
        result = run_intelligence(
            query="book a flight",
            topic="flight",
            research_summary="",
            cognitive_session=session,
        )
        # destination is critical and present → at least partially_ready
        assert result.readiness.state in (ReadinessState.partially_ready, ReadinessState.ready)

    def test_analytics_blocked_counted(self):
        intel_analytics._reset_for_testing()
        run_intelligence("book a flight", "flight", "")  # no session → blocked
        data = intel_analytics.get_analytics()
        assert data["readiness_distribution"]["blocked"] == 1


# ── 4. Approval classification ────────────────────────────────────────────────

class TestApprovalClassification:
    def test_book_is_requires_approval(self):
        result = run_intelligence("book a flight to Goa", "flight", "")
        assert result.execution_plan.approval_level == ApprovalLevel.requires_approval

    def test_buy_is_high_risk(self):
        result = run_intelligence("buy the iPhone 15 now", "iPhone 15", "")
        assert result.execution_plan.approval_level == ApprovalLevel.high_risk

    def test_send_email_is_high_risk(self):
        result = run_intelligence("send email to my boss", "email", "")
        assert result.execution_plan.approval_level == ApprovalLevel.high_risk

    def test_navigate_is_safe(self):
        result = run_intelligence("open amazon website", "amazon", "")
        assert result.execution_plan.approval_level == ApprovalLevel.safe

    def test_register_is_requires_approval(self):
        result = run_intelligence("sign up for the newsletter", "newsletter", "")
        assert result.execution_plan.approval_level == ApprovalLevel.requires_approval

    def test_pay_phrase_elevates_to_high_risk(self):
        result = run_intelligence("book and pay now for flight", "flight", "")
        assert result.execution_plan.approval_level == ApprovalLevel.high_risk


# ── 5. Workflow preparation ───────────────────────────────────────────────────

class TestWorkflowPreparation:
    def test_bootstrap_has_research_topic(self):
        result = run_intelligence("book a hotel in Goa", "hotel in Goa", "Goa hotels summary")
        assert result.bootstrap_facts.research_topic == "hotel in Goa"

    def test_bootstrap_has_research_summary(self):
        result = run_intelligence("book a hotel in Goa", "hotel in Goa", "Goa hotels are expensive")
        assert "expensive" in result.bootstrap_facts.research_summary

    def test_bootstrap_pre_filled_from_session(self):
        session = _FakeSession(["destination"])
        result = run_intelligence("book a flight", "flight", "", cognitive_session=session)
        assert "destination" in result.bootstrap_facts.pre_filled_entities

    def test_bootstrap_goal_tree_summary_not_empty(self):
        result = run_intelligence("book a flight to Delhi", "flight to Delhi", "")
        assert len(result.bootstrap_facts.goal_tree_summary) > 0


# ── 6. Analytics tracking ─────────────────────────────────────────────────────

class TestAnalyticsTracking:
    def test_multiple_runs_accumulate(self):
        intel_analytics._reset_for_testing()
        run_intelligence("research flights", "flights", "")
        run_intelligence("book a flight", "flight", "")
        run_intelligence("buy laptop", "laptop", "")
        data = intel_analytics.get_analytics()
        assert data["research_only_count"] == 1
        assert data["opportunities_detected"] == 2

    def test_recommendations_counted(self):
        intel_analytics._reset_for_testing()
        run_intelligence("book a flight to Goa", "flight", "")
        data = intel_analytics.get_analytics()
        assert data["recommendations_generated"] >= 1

    def test_approval_distribution_tracked(self):
        intel_analytics._reset_for_testing()
        run_intelligence("book a flight", "flight", "")   # requires_approval
        run_intelligence("open amazon", "amazon", "")    # safe (navigate)
        data = intel_analytics.get_analytics()
        assert data["approval_distribution"]["requires_approval"] >= 1
        assert data["approval_distribution"]["safe"] >= 1


# ── 7. AmbientAssistant integration ──────────────────────────────────────────

class TestAmbientAssistantIntegration:
    """Tests that research responses now include an intelligence field."""

    def _make_request(self, message: str):
        from app.schemas.assist import AssistRequest, ReadView
        return AssistRequest(
            conversation_id=str(uuid.uuid4()),
            message=message,
            read_view=ReadView(url="https://example.com", title="Test"),
            context_fingerprint="fp",
            selection_scope="page",
        )

    def _stub_research_session(self, topic: str = "test", with_handoff: bool = False):
        from app.research.models import ResearchSession, ResearchReport, ResearchStatus
        rsession = ResearchSession(
            session_id="stub-sid",
            conversation_id="stub-cid",
            topic=topic,
            status=ResearchStatus.completed,
        )
        rsession.report = ResearchReport(
            executive_summary=f"Summary about {topic}.",
            key_findings=["Finding A"],
            supporting_evidence=[],
            risks=[],
            open_questions=[],
            recommended_actions=[],
            confidence_score=0.8,
        )
        return rsession, None

    def test_research_response_has_intelligence_field(self):
        from app.assist.ambient_assistant import run
        req = self._make_request("research flights from Hyderabad to Goa")
        with patch("app.research.engine.run_research",
                   return_value=self._stub_research_session("flights")):
            resp = run(req)
        assert resp.intelligence is not None

    def test_pure_research_intelligence_not_detected(self):
        from app.assist.ambient_assistant import run
        req = self._make_request("research the history of Python")
        with patch("app.research.engine.run_research",
                   return_value=self._stub_research_session("history of Python")):
            resp = run(req)
        assert resp.intelligence.opportunity.detected is False

    def test_book_research_intelligence_detected(self):
        from app.assist.ambient_assistant import run
        req = self._make_request("research and book a flight to Mumbai")
        with patch("app.research.engine.run_research",
                   return_value=self._stub_research_session("flight to Mumbai")):
            resp = run(req)
        assert resp.intelligence.opportunity.detected is True
        assert resp.intelligence.execution_plan is not None

    def test_recommendations_in_response(self):
        from app.assist.ambient_assistant import run
        req = self._make_request("research and book a hotel in Goa")
        with patch("app.research.engine.run_research",
                   return_value=self._stub_research_session("hotel in Goa")):
            resp = run(req)
        assert len(resp.intelligence.recommendations) >= 1

    def test_bootstrap_in_response(self):
        from app.assist.ambient_assistant import run
        req = self._make_request("research and book a flight to Delhi")
        with patch("app.research.engine.run_research",
                   return_value=self._stub_research_session("flight to Delhi")):
            resp = run(req)
        assert resp.intelligence.bootstrap_facts is not None

    def test_intelligence_latency_is_int(self):
        from app.assist.ambient_assistant import run
        req = self._make_request("research machine learning")
        with patch("app.research.engine.run_research",
                   return_value=self._stub_research_session("machine learning")):
            resp = run(req)
        assert isinstance(resp.intelligence.latency_ms, int)

    def test_research_report_merged_recommendations(self):
        """Intelligence-generated recommendations should appear in research_report.recommended_actions."""
        from app.assist.ambient_assistant import run
        req = self._make_request("research and book a flight to Goa")
        with patch("app.research.engine.run_research",
                   return_value=self._stub_research_session("flight to Goa")):
            resp = run(req)
        # At minimum, intelligence recommendations merged in
        assert len(resp.research_report.recommended_actions) >= 1

    def test_existing_research_paths_unaffected_summarize(self):
        """Summarize path should not have intelligence field."""
        from app.assist.ambient_assistant import run
        import json
        req = self._make_request("summarize this page")
        mock_summary = json.dumps({
            "tldr": "Summary", "key_points": [], "entities": [], "available_actions": []
        })
        with patch("app.services.ai_service.generate_text", return_value=mock_summary):
            with patch("app.services.followup_service.generate", return_value=[]):
                resp = run(req)
        assert resp.intelligence is None

    def test_existing_research_paths_unaffected_ask(self):
        """Ask path should not have intelligence field."""
        from app.assist.ambient_assistant import run
        req = self._make_request("what is the capital of France?")
        with patch("app.services.ai_service.generate_text", return_value="Paris"):
            resp = run(req)
        assert resp.intelligence is None
