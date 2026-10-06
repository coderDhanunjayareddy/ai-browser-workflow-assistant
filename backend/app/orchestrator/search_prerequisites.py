"""Evidence for dated searches, independent of any particular website."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from app.runtime_state_manager.execution_result import is_successful_execution_result
from app.schemas.response import AnalyzeResponse, SuggestedAction
from app.task_language import affirmative_task_text


_MONTH = r"January|February|March|April|May|June|July|August|September|October|November|December"
_DATE_IN_TASK = re.compile(rf"\b(\d{{1,2}})\s+({_MONTH})\s+(\d{{4}})\b", re.IGNORECASE)
_ROUTE_IN_TASK = re.compile(r"\bfrom\s+([A-Za-z][A-Za-z ]{0,50}?)\s+to\s+([A-Za-z][A-Za-z ]{0,50}?)\s+(?:on|for|at)\b", re.IGNORECASE)
_DATE_CONTROL = re.compile(r"\b(?:departure|depart|outbound|check.?in|travel.?date|date)\b", re.IGNORECASE)
_RESULT_ACTION = re.compile(r"\b(?:cheapest|lowest|least expensive|best fare|select.+result|choose.+result)\b", re.IGNORECASE)
_DATE_ACTION = re.compile(r"\b(?:departure|depart|calendar|date)\b", re.IGNORECASE)
_PRICE = re.compile(r"(?:₹|\$|€|£|\bRs\.?\s*)\s*\d[\d,]*(?:\.\d{2})?", re.IGNORECASE)
_ORIGIN_FIELD = re.compile(r"(?:^|[^a-z])(?:srcinput|source|origin|fromcity|from|pickup)(?:$|[^a-z])", re.IGNORECASE)
_DESTINATION_FIELD = re.compile(r"(?:^|[^a-z])(?:destinput|destination|destcity|tocity|arrival|dropoff)(?:$|[^a-z])", re.IGNORECASE)
_SEARCH_CONTROL = re.compile(r"\b(?:search|find)\b", re.IGNORECASE)


def requested_date(task: str) -> date | None:
    match = _DATE_IN_TASK.search(affirmative_task_text(task))
    if not match:
        return None
    try:
        return datetime.strptime(" ".join(match.groups()), "%d %B %Y").date()
    except ValueError:
        return None


def _requested_route_is_current(task: str, page_context: Any) -> bool:
    match = _ROUTE_IN_TASK.search(affirmative_task_text(task))
    if not match:
        return False
    title = str(getattr(page_context, "title", "") or "").casefold()
    url = str(getattr(page_context, "url", "") or "").replace("_", "-").replace("-", " ").casefold()
    source, destination = (" ".join(part.split()).casefold() for part in match.groups())
    return all(re.search(rf"\b{re.escape(part)}\b", title) or re.search(rf"\b{re.escape(part)}\b", url)
               for part in (source, destination))


def _conflicting_route_link(task: str, page_context: Any, action: SuggestedAction) -> bool:
    route = _ROUTE_IN_TASK.search(affirmative_task_text(task))
    if not route or action.action_type != "click":
        return False
    source, destination = (" ".join(part.split()).casefold() for part in route.groups())
    for item in getattr(page_context, "interactive_elements", []) or []:
        element = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        if str(element.get("selector") or "") != action.target_selector:
            continue
        if str(element.get("role") or "").lower() != "link" and str(element.get("type") or "").lower() != "a":
            return False
        label = str(element.get("accessibility_name") or element.get("text") or "").casefold()
        if not re.search(r"\bto\b", label):
            return False
        if not (source in label or destination in label or re.search(r"\b(?:flight|bus|train|ticket|route)\b", label)):
            return False
        return not (re.search(rf"\b{re.escape(source)}\b", label) and re.search(rf"\b{re.escape(destination)}\b", label))
    return False


def _observed_date(value: str) -> date | None:
    value = " ".join(str(value or "").replace("'", " ").split())
    for fmt in ("%a, %b %d, %Y", "%a, %B %d, %Y", "%A, %b %d, %Y",
                "%A, %B %d, %Y", "%a, %d %b %Y", "%a, %d %B %Y",
                "%A, %d %b %Y", "%A, %d %B %Y",
                "%a %b %d %Y", "%A %B %d %Y",
                "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y",
                "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def observed_date_controls(page_context: Any) -> list[tuple[dict[str, Any], date]]:
    controls: list[tuple[dict[str, Any], date]] = []
    for item in getattr(page_context, "interactive_elements", []) or []:
        element = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        if not element.get("visible") or not element.get("selector"):
            continue
        purpose = " ".join(str(element.get(key) or "") for key in
                           ("selector", "placeholder", "aria_label", "text"))
        if not _DATE_CONTROL.search(purpose):
            continue
        state = dict(element.get("state") or {})
        value = str(state.get("value") or element.get("accessibility_name") or "")
        selected = _observed_date(value)
        if selected:
            controls.append((element, selected))
    return controls


def observed_route_prerequisite_response(
    *, session_id: str, task: str, page_context: Any,
) -> AnalyzeResponse | None:
    """Fill uniquely identified route fields on an observed public search form."""
    match = _ROUTE_IN_TASK.search(affirmative_task_text(task))
    if not match:
        return None
    original_match = _ROUTE_IN_TASK.search(task)
    if original_match and tuple(part.casefold() for part in original_match.groups()) == tuple(
        part.casefold() for part in match.groups()
    ):
        match = original_match
    controls = [item.model_dump() if hasattr(item, "model_dump") else dict(item)
                for item in getattr(page_context, "interactive_elements", []) or []]
    if not any(item.get("visible") and _SEARCH_CONTROL.search(
        str(item.get("accessibility_name") or item.get("aria_label") or item.get("text") or ""))
        and str(item.get("role") or "").lower() in {"button", "link"}
        for item in controls):
        return None
    fields: dict[str, list[dict[str, Any]]] = {"origin": [], "destination": []}
    for item in controls:
        if not item.get("visible") or not item.get("selector"):
            continue
        if str(item.get("role") or "").lower() not in {"textbox", "combobox", "searchbox"}:
            continue
        if str(item.get("input_type") or "").lower() in {"password", "email", "tel", "file"}:
            continue
        identity = " ".join(str(item.get(key) or "") for key in
                            ("selector", "placeholder", "aria_label", "accessibility_name"))
        origin = bool(_ORIGIN_FIELD.search(identity))
        destination = bool(_DESTINATION_FIELD.search(identity))
        if origin != destination:
            fields["origin" if origin else "destination"].append(item)
    if len(fields["origin"]) != 1 or len(fields["destination"]) != 1:
        return None
    for kind, city in zip(("origin", "destination"), match.groups()):
        item = fields[kind][0]
        city = " ".join(city.split())
        observed = " ".join(str((item.get("state") or {}).get("value") or "").split())
        if observed.casefold() == city.casefold():
            continue
        selector = str(item["selector"])
        action = SuggestedAction(
            action_id=f"observed_route_{kind}_{city.casefold().replace(' ', '_')}",
            action_type="fill", target_selector=selector, value=city,
            description=f"Fill the observed {kind} field with {city}",
            reasoning=f"The requested {kind} is not selected in this observed route form; fill this exact field and re-observe.",
            confidence=0.9, safety_level="safe",
            grounding={"source": "dom_snapshot", "selector_id": selector,
                       "accessibility_name": str(item.get("accessibility_name") or ""),
                       "role": item.get("role"), "frame_id": item.get("frame_id") or "top"},
        )
        return AnalyzeResponse(session_id=session_id, outcome_kind="act",
                               analysis=action.reasoning, suggested_actions=[action])
    return None


def _priced_result_blocks(page_context: Any) -> int:
    selectors = set()
    for item in getattr(page_context, "content_blocks", []) or []:
        block = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        selector = str(block.get("selector") or "")
        text = str(block.get("text") or "")
        if selector and _PRICE.search(text):
            selectors.add(selector)
    return len(selectors)


def _exact_date_option(page_context: Any, goal_date: date) -> dict[str, Any] | None:
    matches = []
    for item in getattr(page_context, "interactive_elements", []) or []:
        element = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        if not element.get("visible") or not element.get("selector"):
            continue
        if str(element.get("role") or "").lower() not in {"button", "gridcell", "option"} and str(element.get("type") or "").lower() != "button":
            continue
        state = dict(element.get("state") or {})
        if state.get("disabled") or state.get("aria_disabled"):
            continue
        name = str(element.get("accessibility_name") or element.get("aria_label") or element.get("text") or "")
        if _observed_date(name) == goal_date:
            matches.append(element)
    return matches[0] if len(matches) == 1 else None


def observed_date_prerequisite_response(
    *, session_id: str, task: str, page_context: Any, prior_steps: list[Any],
) -> AnalyzeResponse | None:
    """Continue a dated search from uniquely observed controls before model planning."""
    goal_date = requested_date(task)
    if goal_date is None or not _requested_route_is_current(task, page_context):
        return None
    controls = observed_date_controls(page_context)
    if any(selected == goal_date for _, selected in controls):
        return None
    outbound = [(item, selected) for item, selected in controls
                if re.search(r"depart|outbound", str(item.get("selector") or ""), re.IGNORECASE)]
    candidates = outbound if len(outbound) == 1 else controls
    if len(candidates) != 1:
        return None
    control, selected = candidates[0]
    selector = str(control["selector"])
    prior = [step.model_dump() if hasattr(step, "model_dump") else dict(step) for step in prior_steps]
    opened = any(
        str(step.get("target_selector") or "") == selector
        and is_successful_execution_result(step.get("execution_result"))
        for step in prior
    )
    if opened:
        option = _exact_date_option(page_context, goal_date)
        if option is None:
            return None
        selector = str(option["selector"])
        if any(str(step.get("target_selector") or "") == selector for step in prior):
            return None
        name = str(option.get("accessibility_name") or option.get("aria_label") or option.get("text"))
        description = f'Click the exact observed date option "{name}"'
        reasoning = "The requested date is one unique observed calendar option; select it and re-observe."
        role = option.get("role")
        frame_id = option.get("frame_id") or "top"
    else:
        name = str(control.get("accessibility_name") or control.get("aria_label") or selected.isoformat())
        description = f'Click the observed date control "{name}" to choose {goal_date.isoformat()}'
        reasoning = "The current observed date differs from the requested date; open this exact control and re-observe."
        role = control.get("role")
        frame_id = control.get("frame_id") or "top"
    action = SuggestedAction(
        action_id=f"observed_date_{goal_date.isoformat()}_{'option' if opened else 'control'}",
        action_type="click", target_selector=selector, value=None,
        description=description, reasoning=reasoning, confidence=0.9, safety_level="safe",
        grounding={"source": "dom_snapshot", "selector_id": selector,
                   "accessibility_name": name, "role": role, "frame_id": frame_id},
    )
    return AnalyzeResponse(session_id=session_id, outcome_kind="act",
                           analysis=reasoning, suggested_actions=[action])


def enforce_observed_date_before_result(
    *, task: str, page_context: Any, prior_steps: list[Any], result: AnalyzeResponse,
) -> AnalyzeResponse:
    """Prefer the current date control over a stale date selector or premature result pick.

    Only one observed, purpose-matched control is actionable. A previous
    successful opening is not treated as proof that a date was selected.
    """
    goal_date = requested_date(task)
    actions = list(result.suggested_actions or [])
    if goal_date is None or not actions or result.outcome_kind != "act":
        return result
    action = actions[0]
    description = str(action.description or "")
    if _conflicting_route_link(task, page_context, action) and not observed_date_controls(page_context):
        result.outcome_kind = "ask"
        result.analysis = "The proposed route link conflicts with the route in the user's task. No browser action was dispatched."
        result.clarification_question = "Please expose a matching route or result in the current task, then resume."
        result.suggested_actions = []
        result.intent_dispatch = None
        return result
    wants_date = action.action_type == "click" and bool(_DATE_ACTION.search(description))
    wants_result = action.action_type in {"click", "select_option"} and (
        bool(_RESULT_ACTION.search(description))
        or (action.action_type == "click" and _requested_route_is_current(task, page_context) and not wants_date)
    )
    if not (wants_date or wants_result):
        return result
    controls = observed_date_controls(page_context)
    if any(selected == goal_date for _, selected in controls):
        if _conflicting_route_link(task, page_context, action):
            result.outcome_kind = "ask"
            result.analysis = "The proposed route link conflicts with the route in the user's task. No browser action was dispatched."
            result.clarification_question = "Please expose a matching result, then resume this task."
            result.suggested_actions = []
            result.intent_dispatch = None
            return result
        if wants_result and _priced_result_blocks(page_context) < 2:
            result.outcome_kind = "ask"
            result.analysis = "The requested date is selected, but this observation does not contain a comparable list of priced results. No ranked result was chosen."
            result.clarification_question = "Please expose or submit the results for the selected date, then resume this task."
            result.suggested_actions = []
            result.intent_dispatch = None
        return result
    # A page can show both outbound and return dates. Use an explicit outbound
    # identity only if it is unique; otherwise ask rather than guessing.
    outbound = [(item, selected) for item, selected in controls if re.search(r"depart|outbound", str(item.get("selector") or ""), re.IGNORECASE)]
    candidates = outbound if len(outbound) == 1 else controls
    if len(candidates) != 1:
        if wants_result:
            result.outcome_kind = "ask"
            result.analysis = "The requested date has no unique verified control value in the current observation. No ranked result was chosen."
            result.clarification_question = "Please expose the relevant date control and resume this task."
            result.suggested_actions = []
            result.intent_dispatch = None
        return result
    control, selected = candidates[0]
    selector = str(control["selector"])
    opened = any(
        str((step.model_dump() if hasattr(step, "model_dump") else dict(step)).get("target_selector") or "") == selector
        and is_successful_execution_result(
            (step.model_dump() if hasattr(step, "model_dump") else dict(step)).get("execution_result")
        )
        for step in prior_steps
    )
    if opened:
        if wants_result:
            option = _exact_date_option(page_context, goal_date)
            if option is not None:
                option_name = str(option.get("accessibility_name") or option.get("aria_label") or option.get("text"))
                option_selector = str(option["selector"])
                result.suggested_actions = [SuggestedAction(
                    action_id=f"choose_observed_date_{goal_date.isoformat()}",
                    action_type="click", target_selector=option_selector, value=None,
                    description=f'Click the exact observed date option "{option_name}"',
                    reasoning="The requested date is visible as one exact calendar option; select and re-observe the date control.",
                    confidence=0.9, safety_level="safe",
                    grounding={"source": "dom_snapshot", "selector_id": option_selector,
                               "accessibility_name": option_name, "role": option.get("role"),
                               "frame_id": option.get("frame_id") or "top"},
                )]
                result.intent_dispatch = None
                result.intent_execution = None
                result.execution_orchestrator = None
                result.analysis = "Selecting the single exact observed date option before comparing results."
                return result
            result.outcome_kind = "ask"
            result.analysis = "The requested date is not selected in the current observed control. No result was chosen."
            result.clarification_question = "The date picker has no unique observed option for the requested date. Please expose the intended option, then resume this task."
            result.suggested_actions = []
            result.intent_dispatch = None
        return result
    observed_name = str(control.get("accessibility_name") or control.get("aria_label") or selected.isoformat())
    result.suggested_actions = [SuggestedAction(
        action_id=f"open_observed_date_{goal_date.isoformat()}",
        action_type="click",
        target_selector=selector,
        value=None,
        description=f'Click the observed date control "{observed_name}" to choose {goal_date.isoformat()}',
        reasoning="The current observed date differs from the requested date; open this exact control and re-observe.",
        confidence=0.9,
        safety_level="safe",
        grounding={"source": "dom_snapshot", "selector_id": selector,
                   "accessibility_name": observed_name, "role": control.get("role"),
                   "frame_id": control.get("frame_id") or "top"},
    )]
    result.intent_dispatch = None
    result.intent_execution = None
    result.execution_orchestrator = None
    result.analysis = "The observed date is not the requested date. Opening the uniquely identified current date control first."
    return result
