from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen


BACKEND_URL = "http://localhost:8000"
WHATSAPP_URL = "https://web.whatsapp.com/"
CASES = (
    ("timeout", "navigation timed out after the configured budget", "timed out"),
    ("no_effect", "navigation had no effect and page was unchanged", "did not change"),
    ("authentication", "authentication required; login required", "authentication is required"),
    ("policy", "policy blocked navigation pending confirmation", "safety policy"),
    (
        "internal_contract",
        "failure: Execution message has an invalid canonical action contract.",
        "internal execution validation",
    ),
)


def get_json(path: str) -> dict:
    with urlopen(f"{BACKEND_URL}{path}", timeout=10) as response:
        return json.load(response)


def post_json(path: str, payload: dict) -> tuple[dict, float]:
    request = Request(
        f"{BACKEND_URL}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    with urlopen(request, timeout=30) as response:
        body = json.load(response)
    return body, round((time.perf_counter() - started) * 1000, 1)


def request_payload(case_name: str, execution_result: str) -> dict:
    return {
        "session_id": f"day3-failure-{case_name}-{uuid.uuid4()}",
        "task": "Open WhatsApp",
        "page_context": {
            "url": "chrome://newtab/",
            "title": "New Tab",
            "metadata": {},
            "interactive_elements": [],
            "content_blocks": [],
            "headings": [],
            "selected_text": "",
            "visible_text": "",
            "images": [],
        },
        "prior_steps": [{
            "action_type": "navigate",
            "description": "Open WhatsApp",
            "target_selector": None,
            "value": WHATSAPP_URL,
            "execution_result": execution_result,
            "page_url": "chrome://newtab/",
            "page_title": "New Tab",
            "browser_evidence": {"synthetic_failure_injection": True},
        }],
        "supplemental_context": "",
    }


def main() -> None:
    health = get_json("/health")
    if health.get("status") != "ok" or health.get("db") != "connected":
        raise RuntimeError(f"Canonical runtime is not healthy: {health}")

    results = []
    for case_name, execution_result, expected_fragment in CASES:
        response, latency_ms = post_json("/analyze", request_payload(case_name, execution_result))
        answer = str((response.get("report") or {}).get("answer") or "")
        suggested_actions = response.get("suggested_actions") or []
        passed = (
            response.get("outcome_kind") == "report"
            and response.get("sgv_verified") is True
            and response.get("goal_convergence") is True
            and len(suggested_actions) == 0
            and expected_fragment.lower() in answer.lower()
        )
        results.append({
            "case": case_name,
            "injected_execution_result": execution_result,
            "expected_answer_fragment": expected_fragment,
            "latency_ms": latency_ms,
            "passed": passed,
            "response": response,
        })

    artifact = {
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "method": "live POST /analyze with synthetic prior-step failure evidence",
        "runtime": health.get("runtime"),
        "db": health.get("db"),
        "passed": all(item["passed"] for item in results),
        "results": results,
    }
    output = (
        Path(__file__).resolve().parents[2]
        / "docs"
        / "production_validation"
        / "day3"
        / "robustness"
        / "scenario-6-failure-matrix-live-api.json"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "passed": artifact["passed"],
        "output": str(output),
        "cases": [
            {"case": item["case"], "passed": item["passed"], "latency_ms": item["latency_ms"]}
            for item in results
        ],
    }, indent=2))
    if not artifact["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
