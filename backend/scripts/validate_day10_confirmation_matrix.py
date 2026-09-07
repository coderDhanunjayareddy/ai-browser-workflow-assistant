"""Live, no-side-effect certification for the generic confirmation boundary."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen


CASES = (
    ("send", "delivered_content_and_destination", "http://mail.synthetic.test/review"),
    ("share", "delivered_content_and_destination", "http://drive.synthetic.test/review"),
    ("submit", "delivered_content_and_destination", "http://forms.synthetic.test/review"),
    ("delete", "effect_and_destination", "http://storage.synthetic.test/review"),
    ("purchase", "effect_and_destination", "http://shop.synthetic.test/review"),
    ("account_change", "effect_and_destination", "http://identity.synthetic.test/review"),
)


def post(base_url: str, path: str, payload: dict) -> dict:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def policy_request(operation: str, verification_mode: str, url: str) -> dict:
    origin = url.rsplit("/", 1)[0]
    action_id = f"day10-{operation}"
    submission_id = f"day10-{operation}-subject"
    declaration = {
        "schema_version": "consequential_submission.v1",
        "submission_id": submission_id,
        "operation": operation,
        "destination_entity": f"Synthetic {operation} destination",
        "content_identity": f"Synthetic {operation} content or change",
        "preview_required": True,
        "verification_mode": verification_mode,
    }
    action = {
        "action_id": action_id,
        "action_type": "click",
        "target_selector": f"#confirm-{operation}",
        "value": None,
        "description": "Activate the exact reviewed consequential control",
        "reasoning": "Synthetic policy certification only",
        "confidence": 1.0,
        "safety_level": "safe",
        "consequential_submission": declaration,
    }
    contract = {
        "schema_version": "1.0",
        "dispatch_id": f"day10-dispatch-{operation}",
        "action": action,
        "target_identity": {
            "kind": "element", "selector": action["target_selector"],
            "selector_id": action["target_selector"], "exact_name": f"Confirm {operation}",
            "role": "button", "semantic_kind": "consequential_control",
        },
        "grounding_policy": {
            "ordered_sources": ["stable_selector", "accessibility_name", "verified_screenshot"],
            "accessibility_requires_exact_name": True,
            "screenshot_coordinates_verified": False,
            "screenshot_hash": None,
        },
        "origin": {"origin": origin, "observed_url": url, "target_url": None},
        "browser_binding": {"tab_id": 77, "window_id": 7, "frame_id": "top"},
        "resource_identity": {"url": url, "title": f"Synthetic {operation} review"},
        "expected_effect": {"kind": "target_state_change", "description": "Exact reviewed effect"},
        "safety_class": "safe",
        "idempotency_key": f"day10:77:submission:{submission_id}",
    }
    return {
        "session_id": f"day10-live-{operation}-{time.time_ns()}",
        "origin": url,
        "action": action,
        "execution_contract": contract,
        "provenance": [
            {"source_type": "user", "source_id": "day10-certification", "trust": "trusted", "labels": ["direct_user_request"]},
            {"source_type": "planner", "source_id": action_id, "trust": "untrusted", "labels": ["model_proposed"]},
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    health_started = time.perf_counter()
    with urlopen(f"{args.base_url.rstrip('/')}/health", timeout=10) as response:
        health = json.loads(response.read().decode("utf-8"))
    results = []
    for operation, verification_mode, url in CASES:
        request = policy_request(operation, verification_mode, url)
        started = time.perf_counter()
        evaluation = post(args.base_url, "/policy/evaluate", request)
        confirmation = post(args.base_url, "/policy/confirm", {
            "request": request,
            "ttl_seconds": 120,
            "confirmation_source": "human_sidepanel_certification",
        })
        receipt_id = confirmation["receipt_id"]

        drifted = json.loads(json.dumps(request))
        drifted["action"]["consequential_submission"]["content_identity"] += " DRIFTED"
        drifted["execution_contract"]["action"] = drifted["action"]
        drifted["confirmation_receipt_id"] = receipt_id
        drift_rejection = post(args.base_url, "/policy/enforce", drifted)

        confirmed = {**request, "confirmation_receipt_id": receipt_id}
        first_enforcement = post(args.base_url, "/policy/enforce", confirmed)
        replay_enforcement = post(args.base_url, "/policy/enforce", confirmed)
        passed = all((
            evaluation["allowed"] is False,
            evaluation["policy_decision"] == "allow_with_confirmation",
            evaluation["approval_required"] is True,
            drift_rejection["allowed"] is False,
            first_enforcement["allowed"] is True,
            replay_enforcement["allowed"] is False,
        ))
        results.append({
            "operation": operation,
            "origin": url.rsplit("/", 1)[0],
            "initial_pause": evaluation["policy_decision"],
            "identity_drift_blocked": drift_rejection["allowed"] is False,
            "confirmed_once": first_enforcement["allowed"] is True,
            "duplicate_blocked": replay_enforcement["allowed"] is False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "passed": passed,
        })
    report = {
        "schema_version": "day10_confirmation_matrix.v1",
        "runtime": health.get("runtime"),
        "health_latency_ms": round((time.perf_counter() - health_started) * 1000, 2),
        "no_browser_mutation_dispatched": True,
        "passed": all(item["passed"] for item in results),
        "results": results,
    }
    rendered = json.dumps(report, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
