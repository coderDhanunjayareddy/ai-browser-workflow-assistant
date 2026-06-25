"""
Slice 4 Live Validation — Handoff Protocol
Tests: handoff flag set for research/compare/unknown, not set for summarize/ask,
       response integrity, latency benchmarks.
Provider: No LLM calls needed — handoff path is deterministic.
"""
import io, json, os, sys, time, uuid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

from app.schemas.assist import ReadView, AssistRequest
from app.assist.ambient_assistant import run
from app.conversation import manager as conversation_manager

PASS = "OK"
FAIL = "FAIL"
results: list[dict] = []


def _rv():
    return ReadView(
        url="https://example.com",
        title="Example Page",
        headings=["Example"],
        content_blocks=[{"selector": "p", "text": "Example content about Python web frameworks."}],
        visible_text="Example content about Python web frameworks. FastAPI is fast.",
        metadata={},
    )


def _req(message: str) -> AssistRequest:
    conversation_manager._reset_store_for_testing()
    return AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message=message,
        read_view=_rv(),
        context_fingerprint="test",
        selection_scope="page",
    )


def _record(section: str, label: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    results.append({"section": section, "label": label, "status": status, "detail": detail})
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark}  {label}" + (f"  ({detail})" if detail else ""))
    return ok


# ── SECTION 1: Handoff flag set for fallback intents ─────────────────────────

def section1_handoff_flag():
    print("\n" + "="*60)
    print("SECTION 1 — Handoff flag: fallback intents (no LLM needed)")
    print("="*60)

    fallback_cases = [
        ("research",  "research artificial intelligence"),
        ("research2", "look up the history of Python"),
        ("compare",   "compare iPhone vs Samsung"),
        ("compare2",  "which is better, React or Vue?"),
        ("unknown",   "book me a flight to Tokyo"),
        ("unknown2",  "set a calendar reminder"),
    ]

    for label, message in fallback_cases:
        t0 = time.monotonic()
        resp = run(_req(message))
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        print(f"\n  [{label}]  msg='{message[:40]}'  latency={elapsed_ms}ms")
        _record("1_handoff_flag", f"handoff.available=True [{label}]",
                resp.handoff.available is True, f"got {resp.handoff.available}")
        _record("1_handoff_flag", f"handoff.target=workflow [{label}]",
                resp.handoff.target == "workflow", f"got {resp.handoff.target!r}")
        _record("1_handoff_flag", f"type=not_implemented [{label}]",
                resp.type == "not_implemented")
        _record("1_handoff_flag", f"latency<200ms [{label}]",
                elapsed_ms < 200, f"{elapsed_ms}ms")


# ── SECTION 2: Handoff NOT set for light-path intents ────────────────────────

def section2_no_handoff_for_light():
    print("\n" + "="*60)
    print("SECTION 2 — No handoff for summarize/ask (LLM mocked)")
    print("="*60)

    import json as _json
    from unittest.mock import patch

    summary_json = _json.dumps({
        "tldr": "FastAPI is fast.", "key_points": [],
        "entities": [], "available_actions": [],
    })

    # Summarize
    with patch("app.services.ai_service.generate_text", return_value=summary_json):
        with patch("app.services.followup_service.generate", return_value=[]):
            resp_sum = run(_req("summarize this page"))

    print(f"\n  [summarize]  handoff.available={resp_sum.handoff.available}  target={resp_sum.handoff.target!r}")
    _record("2_no_handoff", "summarize handoff.available=False",
            resp_sum.handoff.available is False)
    _record("2_no_handoff", "summarize handoff.target=None",
            resp_sum.handoff.target is None)

    # Ask
    with patch("app.services.ai_service.generate_text", return_value="FastAPI is fast."):
        resp_ask = run(_req("what is this page about?"))

    print(f"  [ask]        handoff.available={resp_ask.handoff.available}  target={resp_ask.handoff.target!r}")
    _record("2_no_handoff", "ask handoff.available=False",
            resp_ask.handoff.available is False)
    _record("2_no_handoff", "ask handoff.target=None",
            resp_ask.handoff.target is None)


# ── SECTION 3: Response content integrity ────────────────────────────────────

def section3_content_integrity():
    print("\n" + "="*60)
    print("SECTION 3 — Response content integrity alongside handoff")
    print("="*60)

    resp = run(_req("research the latest AI developments"))

    print(f"\n  type={resp.type}  intent={resp.intent}  routed_to={resp.routed_to}")
    print(f"  content (preview): {str(resp.content)[:80]}")
    print(f"  suggested_followups: {resp.suggested_followups}")
    print(f"  handoff: available={resp.handoff.available}  target={resp.handoff.target!r}")

    _record("3_integrity", "response type=not_implemented", resp.type == "not_implemented")
    _record("3_integrity", "routed_to=fallback", resp.routed_to == "fallback")
    _record("3_integrity", "content is non-empty string", bool(str(resp.content)))
    _record("3_integrity", "suggested_followups is list", isinstance(resp.suggested_followups, list))
    _record("3_integrity", "handoff.available=True", resp.handoff.available is True)
    _record("3_integrity", "handoff.target=workflow", resp.handoff.target == "workflow")
    _record("3_integrity", "meta.latency_ms >= 0", resp.meta.latency_ms >= 0)


# ── SECTION 4: Pre-Slice-4 regression — existing behavior unchanged ──────────

def section4_regression():
    print("\n" + "="*60)
    print("SECTION 4 — Regression: Slices 1-3 behavior unchanged")
    print("="*60)

    import json as _json
    from unittest.mock import patch

    summary_json = _json.dumps({
        "tldr": "FastAPI is fast.", "key_points": ["Feature 1"],
        "entities": [], "available_actions": [],
    })

    # Summarize still works
    with patch("app.services.ai_service.generate_text", return_value=summary_json):
        with patch("app.services.followup_service.generate", return_value=["What else?"]):
            resp = run(_req("summarize this page"))
    _record("4_regression", "summarize type=summary", resp.type == "summary")
    _record("4_regression", "summarize intent=summarize", resp.intent == "summarize")
    _record("4_regression", "summarize routed_to=light", resp.routed_to == "light")
    _record("4_regression", "summarize followups preserved", len(resp.suggested_followups) > 0)

    # Ask still works
    with patch("app.services.ai_service.generate_text", return_value="FastAPI answer."):
        resp = run(_req("what is FastAPI?"))
    _record("4_regression", "ask type=answer", resp.type == "answer")
    _record("4_regression", "ask suggested_followups=[] (Option B)", resp.suggested_followups == [])
    _record("4_regression", "ask routed_to=light", resp.routed_to == "light")


# ── Run all ───────────────────────────────────────────────────────────────────

def run_validation():
    print("\nSlice 4 Live Validation — Handoff Protocol")

    section1_handoff_flag()
    section2_no_handoff_for_light()
    section3_content_integrity()
    section4_regression()

    total  = len(results)
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = total - passed

    print(f"\n{'='*60}")
    print(f"VALIDATION COMPLETE — Slice 4")
    print(f"  Total:  {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")

    if failed:
        print("\nFAILED:")
        for r in results:
            if r["status"] == FAIL:
                print(f"  [{r['section']}] {r['label']}  {r['detail']}")

    out = os.path.join(os.path.dirname(__file__), "validation_results_slice4.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"  Results: {out}")

    return failed == 0


if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)
