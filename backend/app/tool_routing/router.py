from __future__ import annotations

import re
import uuid

from app.tool_routing.models import RouteCandidate, ToolRoute, ToolRouteTrace, ToolRoutingRequest
from app.tool_routing.trace_store import record

_RESEARCH = re.compile(r"\b(search|research|find|look up|investigate|compare|latest|news|price|documentation)\b", re.I)
_PAGE_ANSWER = re.compile(r"\b(summarize|summary|explain this|this page|selected text|what does this)\b", re.I)
_GUI = re.compile(r"\b(click|fill|type|drag|upload|download|open the site|use the website|visual|canvas)\b", re.I)
_LOGIN = re.compile(r"\b(my account|my email|my calendar|my drive|logged in|signed in|inbox|private workspace)\b", re.I)
_NATIVE_ALLOWLIST = frozenset({"user_selected_file", "os_keychain_reference", "enterprise_device_certificate"})


def infer_request(task: str, *, current_page_available: bool = False) -> ToolRoutingRequest:
    return ToolRoutingRequest(
        task=task,
        current_page_available=current_page_available,
        requires_current_login=bool(_LOGIN.search(task)),
        requires_gui=bool(_GUI.search(task)),
        requires_dynamic_rendering=False,
        untrusted_research=bool(_RESEARCH.search(task)) and not bool(_LOGIN.search(task)),
    )


def route_task(request: ToolRoutingRequest) -> ToolRouteTrace:
    task = request.task.strip()
    wants_research = bool(_RESEARCH.search(task)) or request.untrusted_research
    wants_page_answer = request.current_page_available and bool(_PAGE_ANSWER.search(task))
    needs_gui = request.requires_gui or bool(_GUI.search(task))
    needs_login = request.requires_current_login or bool(_LOGIN.search(task))
    connector_adequate = bool(request.connector and request.connector_available)
    native_eligible = request.native_capability in _NATIVE_ALLOWLIST

    candidates = [
        RouteCandidate(
            route=ToolRoute.context_answer,
            risk_score=0,
            adequate=wants_page_answer and not needs_gui,
            reason="Uses the already supplied page context; no network or browser control." if wants_page_answer and not needs_gui else "The task is not answerable from supplied page context alone.",
        ),
        RouteCandidate(
            route=ToolRoute.structured_search,
            risk_score=1,
            adequate=wants_research and not needs_gui and not needs_login and not request.requires_dynamic_rendering and not connector_adequate,
            reason="A structured logged-out search can answer the research request without GUI control." if wants_research and not needs_gui and not request.requires_dynamic_rendering and not connector_adequate else "Structured search is inadequate for connected private data, GUI, authenticated, or dynamically rendered work.",
        ),
        RouteCandidate(
            route=ToolRoute.connector_api,
            risk_score=2,
            adequate=connector_adequate and not needs_gui,
            reason=f"The declared {request.connector} connector can perform the operation without page automation." if connector_adequate and not needs_gui else "No adequate connected API was declared for this task.",
        ),
        RouteCandidate(
            route=ToolRoute.isolated_browser,
            risk_score=3,
            adequate=(wants_research or request.requires_dynamic_rendering) and not needs_login,
            reason="Dynamic logged-out exploration is isolated from the user's cookies, profile, downloads, and extensions." if (wants_research or request.requires_dynamic_rendering) and not needs_login else "Isolation cannot satisfy a task that requires the user's authenticated session.",
        ),
        RouteCandidate(
            route=ToolRoute.user_session_browser,
            risk_score=4,
            adequate=needs_gui or needs_login,
            reason="The task needs live GUI interaction or the user's authenticated browser session." if needs_gui or needs_login else "User-session browser control is unnecessary for this task.",
        ),
        RouteCandidate(
            route=ToolRoute.native_messaging_handoff,
            risk_score=5,
            adequate=native_eligible,
            reason="The capability is narrowly allowlisted but requires a separately reviewed native host and explicit user handoff." if native_eligible else "Native messaging is not enabled; the requested capability is absent or not narrowly allowlisted.",
        ),
    ]
    adequate = sorted((item for item in candidates if item.adequate), key=lambda item: item.risk_score)
    selected = adequate[0] if adequate else candidates[4]
    if not adequate:
        selected = RouteCandidate(
            route=ToolRoute.user_session_browser,
            risk_score=4,
            adequate=False,
            reason="No non-GUI route was adequate; pause for user review before browser control.",
        )
        candidates[4] = selected

    explanation = (
        f"Selected {selected.route.value} (risk {selected.risk_score}) because {selected.reason} "
        "It is the lowest-risk adequate route among the evaluated candidates."
    )
    isolation = None
    if selected.route == ToolRoute.isolated_browser:
        isolation = {
            "profile": "ephemeral",
            "logged_out": True,
            "persist_storage": False,
            "downloads": False,
            "extensions": False,
            "service_workers": "blocked",
        }
    return record(ToolRouteTrace(
        trace_id=str(uuid.uuid4()),
        task_summary=task[:240],
        selected_route=selected.route,
        selected_risk_score=selected.risk_score,
        explanation=explanation,
        candidates=candidates,
        requires_user_handoff=selected.route in {ToolRoute.user_session_browser, ToolRoute.native_messaging_handoff},
        isolation=isolation,
    ))
