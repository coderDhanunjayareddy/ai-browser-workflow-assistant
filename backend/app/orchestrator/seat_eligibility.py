"""Observed seat eligibility for reversible, single-traveler selection."""

from __future__ import annotations

import re
from typing import Any

from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.task_language import affirmative_task_text


_SEAT_NUMBER = re.compile(r"\bseat number\s+([A-Za-z0-9-]+)\b", re.IGNORECASE)
_SEAT_PRICE = re.compile(r"\bprice\s*(?:[$€£₹]|Rs\.?\s*)?\s*(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE)
_RESTRICTED = re.compile(r"\b(?:reserved for|only for)\s+(male|female)\b|\b(male|female)\s+only\b", re.IGNORECASE)
_SINGLE_TRAVELER = re.compile(r"\b(?:one|1|single)\s+(?:(?:male|female)\s+)?(?:adult|travell?er|passenger|person|seat)\b", re.IGNORECASE)


def _explicit_gender(task: str) -> str | None:
    text = affirmative_task_text(task)
    male = bool(re.search(r"\b(?:male|man)\s+(?:adult|travell?er|passenger)\b|\b(?:adult|travell?er|passenger)\s+is\s+(?:a\s+)?(?:male|man)\b", text, re.IGNORECASE))
    female = bool(re.search(r"\b(?:female|woman)\s+(?:adult|travell?er|passenger)\b|\b(?:adult|travell?er|passenger)\s+is\s+(?:a\s+)?(?:female|woman)\b", text, re.IGNORECASE))
    if male == female:
        return None
    return "male" if male else "female"


def _seat_controls(page_context: Any) -> list[dict[str, Any]]:
    seats = []
    for item in getattr(page_context, "interactive_elements", []) or []:
        element = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        if not element.get("visible") or not element.get("selector"):
            continue
        if str(element.get("role") or "").casefold() != "button":
            continue
        name = str(element.get("accessibility_name") or element.get("aria_label") or "")
        number = _SEAT_NUMBER.search(name)
        if not number:
            continue
        seats.append({**element, "seat_name": name, "seat_number": number.group(1)})
    return seats


def _seat_action(*, session_id: str, element: dict[str, Any], description: str, reasoning: str, action_id: str) -> AnalyzeResponse:
    selector = str(element["selector"])
    name = str(element["seat_name"])
    action = SuggestedAction(
        action_id=action_id, action_type="click", target_selector=selector,
        value=None, description=description, reasoning=reasoning,
        confidence=0.9, safety_level="safe",
        grounding={"source": "dom_snapshot", "selector_id": selector,
                   "accessibility_name": name,
                   "role": element.get("role"),
                   "frame_id": element.get("frame_id") or "top"},
    )
    return AnalyzeResponse(session_id=session_id, outcome_kind="act",
                           analysis=reasoning, suggested_actions=[action])


def observed_seat_eligibility_response(
    *, session_id: str, task: str, page_context: Any, prior_steps: list[Any],
) -> AnalyzeResponse | None:
    """Choose one observed unrestricted seat when passenger eligibility is unknown.

    Selection is reversible. The response still goes through the mission ledger,
    semantic grounding, policy, and the single browser dispatcher.
    """
    if not _SINGLE_TRAVELER.search(affirmative_task_text(task)):
        return None
    seats = _seat_controls(page_context)
    if len(seats) < 2:
        return None
    prior = [step.model_dump() if hasattr(step, "model_dump") else dict(step)
             for step in prior_steps]
    gender = _explicit_gender(task)
    selected = [seat for seat in seats if "currently selected" in seat["seat_name"].casefold()]
    if len(selected) > 1:
        return AnalyzeResponse(
            session_id=session_id, outcome_kind="ask",
            analysis="Multiple seats are selected for one traveler; the application did not change them.",
            clarification_question="Please review the selected seats in this workflow, then resume.",
            suggested_actions=[],
        )
    if selected:
        seat = selected[0]
        restriction = _RESTRICTED.search(seat["seat_name"])
        required = next((part.casefold() for part in restriction.groups() if part), None) if restriction else None
        if required is None or required == gender:
            return None
        if any(f"deselect observed seat {seat['seat_number']}".casefold() in str(step.get("description") or "").casefold()
               for step in prior):
            return AnalyzeResponse(
                session_id=session_id, outcome_kind="ask",
                analysis="An ineligible seat remained selected after one deselection attempt. No second click was sent.",
                clarification_question="Please review the selected seat in this workflow, then resume.",
                suggested_actions=[],
            )
        return _seat_action(
            session_id=session_id, element=seat,
            description=f"Deselect observed seat {seat['seat_number']} reserved for {required}",
            reasoning="The selected seat has a passenger restriction not established by the task; remove this reversible selection before continuing.",
            action_id=f"deselect_ineligible_seat_{seat['seat_number']}",
        )
    eligible = []
    for seat in seats:
        name = seat["seat_name"].casefold()
        if "availability available" not in name or "currently unselected" not in name:
            continue
        restriction = _RESTRICTED.search(name)
        required = next((part.casefold() for part in restriction.groups() if part), None) if restriction else None
        if required is not None and required != gender:
            continue
        # Unknown restriction wording is not treated as an unrestricted seat.
        if required is None and "berth unreserved" not in name:
            continue
        price = _SEAT_PRICE.search(name)
        if price:
            eligible.append((float(price.group(1).replace(",", "")), seat))
    if not eligible:
        return AnalyzeResponse(
            session_id=session_id, outcome_kind="ask",
            analysis="No available seat with verified passenger eligibility and price is visible. No seat was selected.",
            clarification_question="Please choose an eligible seat in the application or provide the required passenger detail, then resume.",
            suggested_actions=[],
        )
    price, seat = min(eligible, key=lambda candidate: candidate[0])
    if any(f"select observed eligible seat {seat['seat_number']}".casefold() in str(step.get("description") or "").casefold()
           for step in prior):
        return AnalyzeResponse(
            session_id=session_id, outcome_kind="ask",
            analysis="The eligible seat did not remain selected after one click. The click was not repeated.",
            clarification_question="Please review the seat map in this workflow, then resume.",
            suggested_actions=[],
        )
    return _seat_action(
        session_id=session_id, element=seat,
        description=f"Select observed eligible seat {seat['seat_number']} priced {price:g}",
        reasoning="This is the lowest priced available seat in the current observed map whose passenger eligibility is verified; select one seat and re-observe.",
        action_id=f"select_eligible_seat_{seat['seat_number']}",
    )


def enforce_seat_action_eligibility(*, task: str, page_context: Any, result: AnalyzeResponse) -> AnalyzeResponse:
    """Reject a planned click on a seat whose observed restriction is unmet."""
    if result.outcome_kind != "act" or not result.suggested_actions:
        return result
    gender = _explicit_gender(task)
    seats = {seat["selector"]: seat for seat in _seat_controls(page_context)}
    for action in result.suggested_actions:
        if action.action_type != "click":
            continue
        seat = seats.get(action.target_selector)
        if seat is None:
            continue
        restriction = _RESTRICTED.search(seat["seat_name"])
        required = next((part.casefold() for part in restriction.groups() if part), None) if restriction else None
        if required is None or required == gender:
            continue
        result.outcome_kind = "ask"
        result.analysis = "The proposed seat has a passenger restriction that the task does not satisfy. No browser action was dispatched."
        result.clarification_question = "Please choose an unrestricted seat or provide the required passenger detail, then resume this workflow."
        result.suggested_actions = []
        result.intent_dispatch = None
        result.intent_execution = None
        return result
    return result
