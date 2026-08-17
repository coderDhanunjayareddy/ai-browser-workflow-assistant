from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.tool_routing import connectors
from app.tool_routing.isolated_browser import run_isolated_research, validate_public_url
from app.tool_routing.models import ToolRoute, ToolRoutingRequest
from app.tool_routing.router import route_task
from app.tool_routing.trace_store import get, reset_for_testing


@pytest.fixture(autouse=True)
def reset_phase4_state():
    connectors.reset_for_testing()
    reset_for_testing()
    yield
    connectors.reset_for_testing()
    reset_for_testing()


def test_context_answer_is_lowest_risk_when_current_page_is_adequate():
    trace = route_task(ToolRoutingRequest(
        task="Summarize this page",
        current_page_available=True,
        untrusted_research=True,
    ))
    assert trace.selected_route == ToolRoute.context_answer
    assert trace.selected_risk_score == 0
    assert "lowest-risk adequate" in trace.explanation


def test_structured_search_wins_for_logged_out_research_without_gui():
    trace = route_task(ToolRoutingRequest(task="Research browser automation standards", untrusted_research=True))
    assert trace.selected_route == ToolRoute.structured_search
    assert trace.isolation is None


def test_connector_route_wins_when_declared_api_is_adequate():
    trace = route_task(ToolRoutingRequest(
        task="List the latest project records",
        connector="projects",
        connector_available=True,
    ))
    assert trace.selected_route == ToolRoute.connector_api


def test_dynamic_untrusted_research_uses_isolated_logged_out_browser():
    trace = route_task(ToolRoutingRequest(
        task="Research this dynamic site",
        untrusted_research=True,
        requires_dynamic_rendering=True,
    ))
    assert trace.selected_route == ToolRoute.isolated_browser
    assert trace.isolation == {
        "profile": "ephemeral",
        "logged_out": True,
        "persist_storage": False,
        "downloads": False,
        "extensions": False,
        "service_workers": "blocked",
    }


def test_authenticated_or_gui_work_uses_user_session_and_requires_handoff():
    trace = route_task(ToolRoutingRequest(task="Open my inbox and click the newest message"))
    assert trace.selected_route == ToolRoute.user_session_browser
    assert trace.requires_user_handoff is True


def test_native_messaging_is_only_a_handoff_for_narrow_allowlisted_capability():
    allowed = route_task(ToolRoutingRequest(
        task="Use a selected local file",
        native_capability="user_selected_file",
    ))
    denied = route_task(ToolRoutingRequest(
        task="Control the operating system",
        native_capability="arbitrary_os_control",
    ))
    assert allowed.selected_route == ToolRoute.native_messaging_handoff
    assert allowed.requires_user_handoff is True
    assert denied.selected_route != ToolRoute.native_messaging_handoff


def test_route_trace_is_retrievable_and_explains_every_candidate():
    trace = route_task(ToolRoutingRequest(task="Search for current browser documentation", untrusted_research=True))
    stored = get(trace.trace_id)
    assert stored == trace
    assert {candidate.route for candidate in trace.candidates} == set(ToolRoute)
    assert all(candidate.reason for candidate in trace.candidates)


def test_private_and_local_isolated_browser_destinations_are_blocked(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("127.0.0.1", 80))])
    with pytest.raises(ValueError, match="private"):
        validate_public_url("http://example.test/internal")
    with pytest.raises(ValueError, match="private"):
        validate_public_url("http://localhost/admin")


def test_isolated_browser_uses_ephemeral_context_and_closes_it(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(None, None, None, None, ("93.184.216.34", 443))])
    events = []

    class Locator:
        def __init__(self, selector): self.selector = selector
        def inner_text(self, timeout): return "Public research content"
        def evaluate_all(self, script): return [{"text": "Source", "url": "https://example.com/source"}]

    class Page:
        url = "https://example.com/final"
        def set_default_timeout(self, value): events.append(("timeout", value))
        def goto(self, url, **kwargs): events.append(("goto", url, kwargs))
        def title(self): return "Example"
        def locator(self, selector): return Locator(selector)

    class Context:
        def clear_cookies(self): events.append(("cookies", "cleared"))
        def route(self, pattern, handler): events.append(("route_guard", pattern))
        def new_page(self): return Page()
        def close(self): events.append(("context", "closed"))

    class Browser:
        def new_context(self, **kwargs): events.append(("context_options", kwargs)); return Context()
        def close(self): events.append(("browser", "closed"))

    class Chromium:
        def launch(self, **kwargs): events.append(("launch", kwargs)); return Browser()

    class Playwright:
        chromium = Chromium()

    class Manager:
        def __enter__(self): return Playwright()
        def __exit__(self, *args): return None

    result = run_isolated_research("https://example.com", playwright_factory=lambda: Manager())
    options = next(value for key, value in events if key == "context_options")
    assert options["accept_downloads"] is False
    assert options["service_workers"] == "block"
    assert result.isolation["persist_storage"] is False
    assert ("route_guard", "**/*") in events
    assert ("context", "closed") in events
    assert ("browser", "closed") in events


def test_api_connector_route_executes_read_only_handler_and_blocks_mutation():
    connectors.register("catalog", lambda operation, args: {"operation": operation, "count": args["limit"]})
    client = TestClient(app)
    ok = client.post("/tool-routing/connector", json={
        "connector": "catalog", "operation": "list", "arguments": {"limit": 3}, "read_only": True,
    })
    blocked = client.post("/tool-routing/connector", json={
        "connector": "catalog", "operation": "delete", "arguments": {}, "read_only": False,
    })
    assert ok.status_code == 200
    assert ok.json()["trace"]["selected_route"] == "connector_api"
    assert ok.json()["result"]["count"] == 3
    assert blocked.status_code == 409


def test_structured_search_endpoint_refuses_a_query_that_requires_gui_control():
    response = TestClient(app).post("/tool-routing/search", json={
        "query": "Click through the website and research the visual dashboard",
        "max_results": 5,
    })
    assert response.status_code == 409
    assert response.json()["detail"]["selected_route"] == "isolated_browser"
