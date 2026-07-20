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


def test_system_prompt_includes_production_capability_guidance():
    prompt = ai_service.SYSTEM_PROMPT

    assert "open_new_tab" in prompt
    assert "switch_tab" in prompt
    assert "focus_existing_tab" in prompt
    assert "close_tab" in prompt
    assert "MULTI-TAB WORKSPACE" in prompt
    assert "File transfer uses normal browser controls" in prompt
    assert "Existing browser execution understands common widgets" in prompt
    assert "Use EXECUTION FEEDBACK when present" in prompt


def test_system_prompt_includes_mission_review_guidance():
    prompt = ai_service.SYSTEM_PROMPT

    assert "MISSION REVIEW" in prompt
    assert "Mission Snapshot" in prompt
    assert "Completed Objectives" in prompt
    assert "Remaining Objectives" in prompt
    assert "Current Focus" in prompt
    assert "Evidence Available" in prompt
    assert "Evidence Missing" in prompt


def test_system_prompt_respects_completed_objectives():
    prompt = ai_service.SYSTEM_PROMPT.lower()

    assert "completed objectives as immutable" in prompt
    assert "do not reopen" in prompt
    assert "repeat already completed work" in prompt


def test_system_prompt_requires_evidence_sufficiency_before_browsing():
    prompt = ai_service.SYSTEM_PROMPT

    assert "if enough evidence exists" in prompt
    assert 'outcome_kind "report"' in prompt
    assert "instead of unnecessary navigation" in prompt


def test_system_prompt_uses_execution_feedback_to_avoid_repeats():
    prompt = ai_service.SYSTEM_PROMPT

    assert "Previous Action Result" in prompt
    assert "no_effect" in prompt
    assert "semantic_mismatch" in prompt
    assert "recovery_failed" in prompt
    assert "do not repeat the same selector/action" in prompt


def test_system_prompt_advances_to_next_subgoal():
    prompt = ai_service.SYSTEM_PROMPT.lower()

    assert "advance to the next remaining objective or subgoal" in prompt
    assert "instead of restarting the workflow" in prompt


def test_system_prompt_prefers_extraction_over_unnecessary_navigation():
    prompt = ai_service.SYSTEM_PROMPT.lower()

    assert "prefer extraction or summarization" in prompt
    assert "unnecessary navigation" in prompt
    assert "finish with outcome_kind" in prompt
    assert "no suggested_actions" in prompt


def test_system_prompt_includes_mission_operating_modes():
    prompt = ai_service.SYSTEM_PROMPT

    assert "MISSION OPERATING MODE" in prompt
    assert "SEARCH" in prompt
    assert "COLLECT" in prompt
    assert "EXTRACT" in prompt
    assert "VERIFY" in prompt
    assert "COMPARE" in prompt
    assert "REPORT" in prompt
    assert "what evidence is required before changing modes" in prompt


def test_system_prompt_transitions_from_search_collect_to_extract_report():
    prompt = ai_service.SYSTEM_PROMPT

    assert "Do not remain in SEARCH or COLLECT once sufficient evidence exists" in prompt
    assert "EXTRACT to capture visible requested information immediately" in prompt
    assert "REPORT to stop browsing and answer" in prompt


def test_system_prompt_includes_domain_capability_reasoning():
    prompt = ai_service.SYSTEM_PROMPT.lower()

    assert "domain and capability reasoning" in prompt
    assert "user's actual goal" in prompt
    assert "capability required" in prompt
    assert "current website can realistically satisfy" in prompt
    assert "more appropriate application or authoritative source" in prompt


def test_system_prompt_avoids_impossible_actions_on_unsuitable_sites():
    prompt = ai_service.SYSTEM_PROMPT.lower()

    assert "messaging applications are not music platforms" in prompt
    assert "report impossibility" in prompt
    assert "when it cannot" in prompt


def test_system_prompt_guides_common_task_categories_to_suitable_sources():
    prompt = ai_service.SYSTEM_PROMPT.lower()

    assert "official product pages are authoritative for pricing" in prompt
    assert "search engines are discovery mechanisms" in prompt
    assert "documentation research should prefer official docs" in prompt
    assert "job searches should prefer job platforms" in prompt
    assert "reuse authenticated sessions" in prompt


def test_system_prompt_requires_continuous_website_suitability_review():
    prompt = ai_service.SYSTEM_PROMPT.lower()

    assert "continuously re-evaluate website suitability" in prompt
    assert "stay when the site can satisfy the goal" in prompt
    assert "search or navigate elsewhere when it cannot" in prompt


def test_planner_contract_top_level_schema_unchanged():
    assert set(AnalyzeResponse.model_fields) == {
        "session_id",
        "analysis",
        "outcome_kind",
        "suggested_actions",
        "clarification_question",
        "report",
        "replan",
        "sgv_verified",
        "goal_convergence",
    }


def test_parse_response_report_outcome():
    raw = _raw(outcome_kind="report", suggested_actions=[],
               report={"answer": "₹15,299.00", "claim": "price already visible in accessibility name"})
    resp = ai_service.parse_response(raw, "s1")
    assert resp.outcome_kind == "report"
    assert resp.suggested_actions == []
    assert resp.report is not None
    assert resp.report.answer == "₹15,299.00"
    assert resp.report.claim == "price already visible in accessibility name"


@pytest.mark.parametrize(
    ("action_type", "value"),
    [
        ("open_new_tab", "https://example.com/research"),
        ("switch_tab", "title:Example Research"),
        ("focus_existing_tab", "purpose:Compare product details"),
        ("close_tab", "tab:42"),
    ],
)
def test_parse_response_accepts_existing_tab_control_actions(action_type, value):
    raw = _raw(suggested_actions=[{
        "action_id": f"{action_type}_1",
        "action_type": action_type,
        "target_selector": None,
        "value": value,
        "description": f"{action_type} for multi-tab workflow",
        "reasoning": "The tab workspace identifies the target tab explicitly.",
        "confidence": 0.8,
        "safety_level": "safe",
    }])

    resp = ai_service.parse_response(raw, "s1")

    assert resp.outcome_kind == "act"
    assert resp.suggested_actions[0].action_type == action_type
    assert resp.suggested_actions[0].value == value


def test_parse_response_normalizes_report_action_to_report_outcome():
    raw = _raw(suggested_actions=[{
        "action_id": "extract_price_001",
        "action_type": "report",
        "target_selector": None,
        "value": "â‚¹15,299.00",
        "description": "Extract the price from the current page.",
        "reasoning": "The price is already visible on the product page.",
        "confidence": 1.0,
        "safety_level": "safe",
    }])
    resp = ai_service.parse_response(raw, "s1")
    assert resp.outcome_kind == "report"
    assert resp.suggested_actions == []
    assert resp.report is not None
    assert resp.report.answer == "â‚¹15,299.00"
    assert resp.report.claim == "The price is already visible on the product page."


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


def test_debug_logging_is_safe_for_cp1252_stdout(monkeypatch):
    class Cp1252Stdout:
        encoding = "cp1252"

        def __init__(self):
            self.parts = []

        def write(self, text):
            text.encode(self.encoding)
            self.parts.append(text)

        def flush(self):
            pass

    stream = Cp1252Stdout()
    monkeypatch.setattr(ai_service.sys, "stdout", stream)

    ai_service._safe_debug_print("price " + chr(0x20B9) + "699")

    assert "\\u20b9" in "".join(stream.parts)
