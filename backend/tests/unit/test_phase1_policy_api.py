from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import policy as policy_route
from app.policy.live_engine import LivePolicyEngine
from app.policy.live_store import LivePolicyStore


def payload(*, action_id: str = "act-1", description: str = "Click Continue") -> dict:
    action = {
        "action_id": action_id,
        "action_type": "click",
        "target_selector": "#continue",
        "value": None,
        "description": description,
        "reasoning": "Do the requested step",
        "confidence": 0.95,
        "safety_level": "caution",
    }
    return {
        "session_id": "api-session",
        "origin": "https://example.com/checkout",
        "action": action,
        "execution_contract": {
            "schema_version": "1.0",
            "dispatch_id": f"dispatch:{action_id}",
            "action": action,
            "target_identity": {"selector": "#continue", "exact_name": "Continue"},
            "grounding_policy": {
                "ordered_sources": ["stable_selector", "accessibility_name", "verified_screenshot"],
                "accessibility_requires_exact_name": True,
                "screenshot_coordinates_verified": False,
                "screenshot_hash": None,
            },
            "origin": {"origin": "https://example.com", "observed_url": "https://example.com/checkout"},
            "browser_binding": {"tab_id": 1, "window_id": 1, "frame_id": "top"},
            "resource_identity": {"url": "https://example.com/checkout", "title": "Checkout"},
            "expected_effect": {"kind": "target_state_change", "description": "state changes"},
            "safety_class": "caution",
            "idempotency_key": f"api-session:1:{action_id}",
        },
        "provenance": [
            {"source_type": "user", "source_id": "task", "trust": "trusted", "labels": ["direct_user_task"]},
            {"source_type": "planner", "source_id": action_id, "trust": "untrusted", "labels": ["model_proposed"]},
            {"source_type": "page", "source_id": "page", "trust": "untrusted", "labels": ["page_observation"]},
        ],
    }


def client(monkeypatch) -> TestClient:
    store = LivePolicyStore()
    monkeypatch.setattr(policy_route, "live_policy_store", store)
    monkeypatch.setattr(policy_route, "live_policy_engine", LivePolicyEngine(store=store))
    app = FastAPI()
    app.include_router(policy_route.router)
    return TestClient(app)


def test_api_requires_and_consumes_narrow_confirmation(monkeypatch):
    api = client(monkeypatch)
    request = payload(action_id="purchase-1", description="Place order")

    denied = api.post("/policy/enforce", json=request)
    assert denied.status_code == 200
    assert denied.json()["allowed"] is False
    assert denied.json()["decision_reason"] == "valid_confirmation_receipt_required"

    issued = api.post("/policy/confirm", json={"request": request, "confirmation_source": "human_sidepanel"})
    assert issued.status_code == 200
    receipt_id = issued.json()["receipt_id"]

    request["confirmation_receipt_id"] = receipt_id
    allowed = api.post("/policy/enforce", json=request)
    assert allowed.status_code == 200
    assert allowed.json()["allowed"] is True

    replay = api.post("/policy/enforce", json=request)
    assert replay.json()["allowed"] is False

    audit = api.get("/policy/audit/api-session")
    assert audit.status_code == 200
    event_types = {event["event_type"] for event in audit.json()}
    assert {"confirmation_issued", "receipt_consumed", "execution_allowed", "execution_denied"} <= event_types


def test_api_rejects_non_human_confirmation_source(monkeypatch):
    api = client(monkeypatch)
    response = api.post(
        "/policy/confirm",
        json={"request": payload(description="Place order"), "confirmation_source": "planner"},
    )
    assert response.status_code == 422
