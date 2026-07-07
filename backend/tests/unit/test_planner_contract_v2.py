"""
Planner Contract V2 — response schema + parser unit tests.

The planner's contract widens from "always an action" to "one typed outcome, of
one of five kinds" (act, report, wait, ask, replan). These tests exercise the
schema defaults (backward compatibility) and app.services.ai_service.parse_response
directly with raw JSON strings, with no provider/network mocking required.
"""
import json

import pytest

from app.schemas.response import AnalyzeResponse, ReportOutcome, ReplanOutcome, SuggestedAction
from app.services import ai_service


# ── Schema: additive, defaults preserve today's behavior ─────────────────────

def test_outcome_kind_defaults_to_act_for_untouched_construction():
    resp = AnalyzeResponse(session_id="s", analysis="", suggested_actions=[])
    assert resp.outcome_kind == "act"
    assert resp.report is None
    assert resp.replan is None


def test_report_outcome_requires_a_claim():
    with pytest.raises(Exception):
        ReportOutcome()  # claim is required; answer is optional
    ro = ReportOutcome(claim="price already visible")
    assert ro.answer is None


def test_replan_outcome_requires_a_reason():
    with pytest.raises(Exception):
        ReplanOutcome()


# ── Parser: app.services.ai_service.parse_response ───────────────────────────

def _raw(**overrides) -> str:
    body = {
        "analysis": "next step",
        "outcome_kind": "act",
        "suggested_actions": [{
            "action_id": "a1", "action_type": "click", "target_selector": "#go",
            "value": None, "description": "click go", "reasoning": "r",
            "confidence": 1.0, "safety_level": "safe",
        }],
    }
    body.update(overrides)
    return json.dumps(body)


def test_parse_response_act_outcome_unchanged():
    resp = ai_service.parse_response(_raw(), "s1")
    assert resp.outcome_kind == "act"
    assert len(resp.suggested_actions) == 1
    assert resp.suggested_actions[0].action_type == "click"


def test_parse_response_report_outcome():
    raw = _raw(outcome_kind="report", suggested_actions=[],
               report={"answer": "₹15,299.00", "claim": "price already visible in accessibility name"})
    resp = ai_service.parse_response(raw, "s1")
    assert resp.outcome_kind == "report"
    assert resp.suggested_actions == []
    assert resp.report is not None
    assert resp.report.answer == "₹15,299.00"
    assert resp.report.claim == "price already visible in accessibility name"


def test_parse_response_replan_outcome():
    raw = _raw(outcome_kind="replan", suggested_actions=[],
               replan={"reason": "current approach is not working"})
    resp = ai_service.parse_response(raw, "s1")
    assert resp.outcome_kind == "replan"
    assert resp.replan is not None
    assert resp.replan.reason == "current approach is not working"


def test_parse_response_ask_outcome_reuses_clarification_question():
    raw = _raw(outcome_kind="ask", suggested_actions=[],
               clarification_question="What is your delivery address?")
    resp = ai_service.parse_response(raw, "s1")
    assert resp.outcome_kind == "ask"
    assert resp.clarification_question == "What is your delivery address?"


def test_parse_response_unknown_outcome_kind_fails_open_to_act():
    raw = _raw(outcome_kind="not_a_real_kind")
    resp = ai_service.parse_response(raw, "s1")
    assert resp.outcome_kind == "act"


def test_parse_response_report_without_claim_is_dropped_not_errored():
    # a malformed report object (missing required "claim") must not raise —
    # it degrades to report=None rather than breaking the response.
    raw = _raw(outcome_kind="report", suggested_actions=[], report={"answer": "42"})
    resp = ai_service.parse_response(raw, "s1")
    assert resp.report is None


def test_parse_response_missing_outcome_kind_defaults_to_act():
    # Backward compatibility: a response with no "outcome_kind" key at all
    # (as every pre-V2 provider response would look) must parse exactly as before.
    body = {
        "analysis": "next step",
        "suggested_actions": [{
            "action_id": "a1", "action_type": "fill", "target_selector": "#u",
            "value": "x", "description": "fill", "reasoning": "r",
            "confidence": 1.0, "safety_level": "safe",
        }],
    }
    resp = ai_service.parse_response(json.dumps(body), "s1")
    assert resp.outcome_kind == "act"
    assert resp.suggested_actions[0].action_type == "fill"
