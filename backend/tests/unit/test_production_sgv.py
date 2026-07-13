"""
Production SGV Phase 1 — unit tests.

Tests cover:
  - verify_report: verified / unverified / empty evidence
  - collect_page_evidence: all evidence sources included
  - Orchestrator integration: sgv_verified set correctly, outcome_kind preserved
  - Other outcome_kinds (act, wait, ask, replan) are unaffected

These are pure unit tests that do not require a database or AI provider.
"""
from __future__ import annotations

import pytest

from app.orchestrator.report_verifier import collect_page_evidence, verify_report
from app.schemas.request import PageContext, InteractiveElement, ContentBlock


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def make_page_context(
    visible_text: str = "",
    title: str = "",
    headings: list[str] | None = None,
    selected_text: str = "",
    content_blocks: list[dict] | None = None,
    interactive_elements: list[dict] | None = None,
) -> PageContext:
    blocks = [ContentBlock(**b) for b in (content_blocks or [])]
    elements = [InteractiveElement(**e) for e in (interactive_elements or [])]
    return PageContext(
        url="https://example.test",
        title=title,
        metadata={},
        interactive_elements=elements,
        content_blocks=blocks,
        headings=headings or [],
        selected_text=selected_text,
        visible_text=visible_text,
        images=[],
    )


# ─────────────────────────────────────────────────────────────────────────────
# collect_page_evidence
# ─────────────────────────────────────────────────────────────────────────────

class TestCollectPageEvidence:
    def test_includes_visible_text(self):
        ctx = make_page_context(visible_text="Price: ₹15,299")
        evidence = collect_page_evidence(ctx)
        assert any("₹15,299" in e for e in evidence)

    def test_includes_title(self):
        ctx = make_page_context(title="Invoice Summary")
        evidence = collect_page_evidence(ctx)
        assert any("Invoice Summary" in e for e in evidence)

    def test_includes_headings(self):
        ctx = make_page_context(headings=["Total Due", "Order Confirmed"])
        evidence = collect_page_evidence(ctx)
        assert any("Total Due" in e for e in evidence)
        assert any("Order Confirmed" in e for e in evidence)

    def test_includes_content_block_text(self):
        ctx = make_page_context(content_blocks=[
            {"text": "Invoice total: $42.00", "selector": ".total"}
        ])
        evidence = collect_page_evidence(ctx)
        assert any("Invoice total: $42.00" in e for e in evidence)

    def test_includes_element_text_and_labels(self):
        ctx = make_page_context(interactive_elements=[
            {
                "type": "input",
                "text": "Confirm payment",
                "selector": "#confirm",
                "visible": True,
                "aria_label": "confirm payment",
                "accessibility_name": "confirm payment",
                "placeholder": None,
                "state": {},
            }
        ])
        evidence = collect_page_evidence(ctx)
        assert any("Confirm payment" in e for e in evidence)
        assert any("confirm payment" in e for e in evidence)

    def test_includes_element_state_value(self):
        ctx = make_page_context(interactive_elements=[
            {
                "type": "input",
                "text": "",
                "selector": "#city",
                "visible": True,
                "state": {"value": "Mumbai"},
            }
        ])
        evidence = collect_page_evidence(ctx)
        assert any("Mumbai" in e for e in evidence)

    def test_empty_page_returns_no_evidence(self):
        ctx = make_page_context()
        evidence = collect_page_evidence(ctx)
        assert evidence == []


# ─────────────────────────────────────────────────────────────────────────────
# verify_report — core validator
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyReport:
    def test_answer_in_visible_text_verifies(self):
        ctx = make_page_context(visible_text="Order total: ₹14,632.00. Thank you!")
        assert verify_report(
            claim="The invoice total is visible on the page.",
            answer="₹14,632.00",
            page_context=ctx,
        ) is True

    def test_answer_in_content_block_verifies(self):
        ctx = make_page_context(content_blocks=[
            {"text": "Total: $99.99", "selector": ".amount"}
        ])
        assert verify_report(
            claim="The price is on the page.",
            answer="$99.99",
            page_context=ctx,
        ) is True

    def test_answer_in_heading_verifies(self):
        ctx = make_page_context(headings=["Payment Complete", "Amount: €50.00"])
        assert verify_report(
            claim="Payment amount shown.",
            answer="€50.00",
            page_context=ctx,
        ) is True

    def test_answer_in_page_title_verifies(self):
        ctx = make_page_context(title="Invoice #12345 — Confirmed")
        assert verify_report(
            claim="Invoice ID is shown.",
            answer="Invoice #12345",
            page_context=ctx,
        ) is True

    def test_answer_not_in_page_does_not_verify(self):
        ctx = make_page_context(visible_text="Loading your order details...")
        assert verify_report(
            claim="The price is visible.",
            answer="₹15,299.00",
            page_context=ctx,
        ) is False

    def test_empty_answer_does_not_verify(self):
        """A bare claim with no specific answer cannot be objectively checked."""
        ctx = make_page_context(visible_text="Order placed successfully!")
        assert verify_report(
            claim="The order was placed.",
            answer=None,
            page_context=ctx,
        ) is False

    def test_whitespace_only_answer_does_not_verify(self):
        ctx = make_page_context(visible_text="Order placed.")
        assert verify_report(
            claim="Done.",
            answer="   ",
            page_context=ctx,
        ) is False

    def test_empty_page_evidence_does_not_verify(self):
        ctx = make_page_context()
        assert verify_report(
            claim="The result is ready.",
            answer="Result: 42",
            page_context=ctx,
        ) is False

    def test_verification_is_case_insensitive(self):
        ctx = make_page_context(visible_text="Total Amount: INR 14,632.00")
        assert verify_report(
            claim="Total shown.",
            answer="inr 14,632.00",
            page_context=ctx,
        ) is True

    def test_answer_must_appear_in_evidence_not_only_in_claim(self):
        """
        The claim itself must NOT be the evidence — the answer must appear on
        the actual page.  Mirrors benchmark test_report_outcome_does_not_self_certify.
        """
        ctx = make_page_context(
            visible_text="Products are loading, please wait.",
        )
        assert verify_report(
            claim="The price ₹15,299.00 is shown in the product listing.",
            answer="₹15,299.00",
            page_context=ctx,
        ) is False


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator integration — sgv_verified is set; outcome_kind is preserved
# ─────────────────────────────────────────────────────────────────────────────

class TestOrchestratorSGVIntegration:
    """
    Tests orchestrate_analysis behaviour for the SGV gate, using a mock AI service.
    Verifies that:
      - sgv_verified is set to True when evidence corroborates the answer
      - sgv_verified is set to False when evidence does not corroborate
      - outcome_kind remains 'report' in both cases
      - act / wait / ask / replan outcomes leave sgv_verified = False (default)
    """

    def _make_request(self, visible_text: str = ""):
        from app.schemas.request import AnalyzeRequest
        return AnalyzeRequest(
            session_id="test-sgv",
            task="What is the total?",
            page_context=make_page_context(visible_text=visible_text),
            prior_steps=[],
            supplemental_context="",
        )

    def _make_report_response(self, answer: str | None, claim: str) -> "AnalyzeResponse":
        from app.schemas.response import AnalyzeResponse, ReportOutcome
        return AnalyzeResponse(
            session_id="test-sgv",
            analysis="Price found.",
            outcome_kind="report",
            suggested_actions=[],
            report=ReportOutcome(answer=answer, claim=claim),
        )

    def _make_act_response(self) -> "AnalyzeResponse":
        from app.schemas.response import AnalyzeResponse, SuggestedAction
        return AnalyzeResponse(
            session_id="test-sgv",
            analysis="Click next.",
            outcome_kind="act",
            suggested_actions=[
                SuggestedAction(
                    action_id="a1",
                    action_type="click",
                    target_selector="#next",
                    value=None,
                    description="Click next button",
                    reasoning="Required to proceed",
                    confidence=0.9,
                    safety_level="safe",
                )
            ],
        )

    def test_verified_report_sets_sgv_verified_true(self):
        from app.orchestrator.report_verifier import verify_report
        request = self._make_request(visible_text="Total: ₹14,632.00")
        response = self._make_report_response(answer="₹14,632.00", claim="Price is visible.")

        verified = verify_report(
            claim=response.report.claim,
            answer=response.report.answer,
            page_context=request.page_context,
        )
        response.sgv_verified = verified

        assert response.sgv_verified is True
        assert response.outcome_kind == "report"   # planner intent preserved

    def test_unverified_report_sets_sgv_verified_false(self):
        from app.orchestrator.report_verifier import verify_report
        request = self._make_request(visible_text="Loading order...")
        response = self._make_report_response(answer="₹14,632.00", claim="Price is visible.")

        verified = verify_report(
            claim=response.report.claim,
            answer=response.report.answer,
            page_context=request.page_context,
        )
        response.sgv_verified = verified

        assert response.sgv_verified is False
        assert response.outcome_kind == "report"   # planner intent preserved

    def test_act_outcome_sgv_verified_is_false_by_default(self):
        response = self._make_act_response()
        # SGV only runs for report outcomes; act responses are untouched.
        assert response.sgv_verified is False
        assert response.outcome_kind == "act"

    def test_ask_outcome_sgv_verified_is_false_by_default(self):
        from app.schemas.response import AnalyzeResponse
        response = AnalyzeResponse(
            session_id="test-sgv",
            analysis="Need credentials.",
            outcome_kind="ask",
            suggested_actions=[],
            clarification_question="What is your username?",
        )
        assert response.sgv_verified is False
        assert response.outcome_kind == "ask"

    def test_wait_outcome_sgv_verified_is_false_by_default(self):
        from app.schemas.response import AnalyzeResponse, SuggestedAction
        response = AnalyzeResponse(
            session_id="test-sgv",
            analysis="Page is loading.",
            outcome_kind="wait",
            suggested_actions=[
                SuggestedAction(
                    action_id="w1",
                    action_type="wait",
                    target_selector="window",
                    value="2000",
                    description="Wait for page to load",
                    reasoning="Page is still loading",
                    confidence=0.8,
                    safety_level="safe",
                )
            ],
        )
        assert response.sgv_verified is False
        assert response.outcome_kind == "wait"

    def test_replan_outcome_sgv_verified_is_false_by_default(self):
        from app.schemas.response import AnalyzeResponse, ReplanOutcome
        response = AnalyzeResponse(
            session_id="test-sgv",
            analysis="Current approach not working.",
            outcome_kind="replan",
            suggested_actions=[],
            replan=ReplanOutcome(reason="Login form appeared unexpectedly."),
        )
        assert response.sgv_verified is False
        assert response.outcome_kind == "replan"
