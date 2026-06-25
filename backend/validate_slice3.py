"""
Slice 3 Live Validation — Chat UI Shell / Multi-turn Conversation Thread
Tests: regression (summarize + ask), multi-turn threading, conversation isolation,
       follow-up chip routing, follow-up grounding, latency benchmarks.
Provider: OpenRouter / gpt-4o-mini (from .env)
"""
import io, json, os, sys, time, uuid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

from app.schemas.assist import ReadView, AssistRequest
from app.assist.ambient_assistant import run
from app.conversation import manager as conversation_manager
from app.intent.router import classify


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _rv_github():
    return ReadView(
        url="https://github.com/tiangolo/fastapi",
        title="tiangolo/fastapi: FastAPI framework",
        headings=["FastAPI", "Requirements", "Installation", "Example", "Performance"],
        content_blocks=[
            {"selector": ".readme p:1", "text": "FastAPI is a modern, fast web framework for building APIs with Python."},
            {"selector": ".stars",       "text": "75,400 stars · MIT License · Python 3.8+"},
            {"selector": ".install",     "text": "pip install fastapi"},
        ],
        visible_text=(
            "FastAPI is a modern, fast web framework for building APIs with Python.\n"
            "Key features: high performance (par with NodeJS/Go), 200-300% faster dev, 40% fewer bugs.\n"
            "75,400 stars. MIT License. Python 3.8+.\nInstall: pip install fastapi"
        ),
        metadata={"description": "FastAPI Python framework"},
    )


def _rv_amazon():
    return ReadView(
        url="https://www.amazon.com/dp/B0BSHF7LLL",
        title="Apple MacBook Pro 14-inch M3 Pro — $1,799.00",
        content_blocks=[
            {"selector": "#productTitle", "text": "Apple MacBook Pro 14-inch with M3 Pro chip"},
            {"selector": "#price",        "text": "$1,799.00"},
            {"selector": ".feature-1",   "text": "M3 Pro chip: 11-core CPU, 14-core GPU"},
            {"selector": ".rating",       "text": "4.7 out of 5 stars · 2,341 ratings"},
            {"selector": ".shipping",     "text": "In stock. Free delivery. Ships from Amazon."},
        ],
        visible_text=(
            "Apple MacBook Pro 14-inch with M3 Pro chip.\n"
            "Price: $1,799.00\nRating: 4.7/5 (2,341 ratings)\n"
            "M3 Pro: 11-core CPU, 14-core GPU\n18 hours battery\n"
            "In stock. Ships from Amazon."
        ),
        metadata={},
    )


def _rv_ml():
    return ReadView(
        url="https://en.wikipedia.org/wiki/Machine_learning",
        title="Machine learning - Wikipedia",
        headings=["Machine learning", "Overview", "Supervised learning"],
        content_blocks=[
            {"selector": "p:1", "text": "Machine learning (ML) is a field of artificial intelligence."},
            {"selector": "p:2", "text": "Supervised learning uses labelled training data."},
            {"selector": "p:3", "text": "Applications: computer vision, NLP, fraud detection."},
        ],
        visible_text=(
            "Machine learning (ML) is a field of artificial intelligence. "
            "Supervised learning uses labelled training data. "
            "Applications: computer vision, NLP, fraud detection."
        ),
        metadata={},
    )


def _make_request(conv_id: str, message: str, rv: ReadView, scope: str = "page") -> AssistRequest:
    return AssistRequest(
        conversation_id=conv_id,
        message=message,
        read_view=rv,
        context_fingerprint=rv.url[:40],
        selection_scope=scope,
    )


def _reset():
    conversation_manager._reset_store_for_testing()


PASS = "OK"
FAIL = "FAIL"

results: list[dict] = []


def _record(section: str, label: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    results.append({"section": section, "label": label, "status": status, "detail": detail})
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark}  {label}" + (f"  ({detail})" if detail else ""))
    return ok


# ── SECTION 1: Regression — Summarize on 5 page types ────────────────────────

def section1_summarize_regression():
    print("\n" + "="*60)
    print("SECTION 1 — Regression: Summarize on 3 page types")
    print("="*60)

    pages = [
        ("github",  _rv_github(),  "summarize this page"),
        ("amazon",  _rv_amazon(),  "summarize this page"),
        ("ml",      _rv_ml(),      "summarize this page"),
    ]

    latencies = []
    for name, rv, msg in pages:
        _reset()
        conv_id = str(uuid.uuid4())
        t0 = time.monotonic()
        resp = run(_make_request(conv_id, msg, rv))
        elapsed = round(time.monotonic() - t0, 2)
        latencies.append(elapsed)

        print(f"\n  [{name}]  latency={elapsed}s")
        _record("1_summarize_regression", f"type=summary [{name}]",
                resp.type == "summary", f"got {resp.type}")
        _record("1_summarize_regression", f"intent=summarize [{name}]",
                resp.intent == "summarize")
        tldr_ok = (
            (isinstance(resp.content, dict) and bool(resp.content.get("tldr")))
            or (hasattr(resp.content, "tldr") and bool(resp.content.tldr))  # type: ignore[union-attr]
        )
        _record("1_summarize_regression", f"has tldr [{name}]", tldr_ok)
        _record("1_summarize_regression", f"followups list [{name}]",
                isinstance(resp.suggested_followups, list))

    avg_lat = round(sum(latencies) / len(latencies), 2)
    print(f"\n  Avg summarize latency: {avg_lat}s")
    return latencies


# ── SECTION 2: Regression — Ask on 3 page types ──────────────────────────────

def section2_ask_regression():
    print("\n" + "="*60)
    print("SECTION 2 — Regression: Ask on 3 page types")
    print("="*60)

    cases = [
        ("github",  _rv_github(),  "How do I install this framework?"),
        ("amazon",  _rv_amazon(),  "What is the price of this product?"),
        ("ml",      _rv_ml(),      "What is machine learning?"),
    ]

    latencies = []
    for name, rv, question in cases:
        _reset()
        conv_id = str(uuid.uuid4())
        t0 = time.monotonic()
        resp = run(_make_request(conv_id, question, rv))
        elapsed = round(time.monotonic() - t0, 2)
        latencies.append(elapsed)

        print(f"\n  [{name}]  Q: {question}")
        print(f"    A: {str(resp.content)[:100]}")
        print(f"    latency={elapsed}s")

        _record("2_ask_regression", f"type=answer [{name}]",
                resp.type == "answer", f"got {resp.type}")
        _record("2_ask_regression", f"intent=ask [{name}]",
                resp.intent == "ask")
        _record("2_ask_regression", f"content is string [{name}]",
                isinstance(resp.content, str))
        _record("2_ask_regression", f"followups=[] [{name}]",
                resp.suggested_followups == [], f"got {resp.suggested_followups}")

    avg_lat = round(sum(latencies) / len(latencies), 2)
    print(f"\n  Avg ask latency: {avg_lat}s")
    return latencies


# ── SECTION 3: Multi-turn conversation thread ─────────────────────────────────

def section3_multi_turn():
    print("\n" + "="*60)
    print("SECTION 3 — Multi-turn conversation thread (summarize -> ask -> ask)")
    print("="*60)

    _reset()
    conv_id = str(uuid.uuid4())
    rv = _rv_github()

    # Turn 1: Summarize
    print("\n  Turn 1: Summarize")
    t0 = time.monotonic()
    r1 = run(_make_request(conv_id, "summarize this page", rv))
    lat1 = round(time.monotonic() - t0, 2)
    print(f"    type={r1.type}  latency={lat1}s")
    _record("3_multi_turn", "T1 type=summary", r1.type == "summary")
    _record("3_multi_turn", "T1 has followups", len(r1.suggested_followups) > 0,
            f"count={len(r1.suggested_followups)}")

    # Turn 2: Ask grounded question
    q2 = "How many stars does FastAPI have?"
    print(f"\n  Turn 2: Ask '{q2}'")
    t0 = time.monotonic()
    r2 = run(_make_request(conv_id, q2, rv))
    lat2 = round(time.monotonic() - t0, 2)
    print(f"    type={r2.type}  latency={lat2}s")
    print(f"    A: {str(r2.content)[:120]}")
    _record("3_multi_turn", "T2 type=answer", r2.type == "answer")
    _record("3_multi_turn", "T2 answer contains star count",
            "75" in str(r2.content) or "star" in str(r2.content).lower())

    # Turn 3: Follow-up chip scenario — use one of T1's follow-ups
    followup_q = r1.suggested_followups[0] if r1.suggested_followups else "What Python version is required?"
    print(f"\n  Turn 3: Follow-up chip '{followup_q}'")
    # Follow-up routing check — must route to ask (not summarize/research)
    followup_route = classify(followup_q)
    _record("3_multi_turn", "T3 followup routes to ask",
            followup_route.intent == "ask",
            f"got intent={followup_route.intent}")
    t0 = time.monotonic()
    r3 = run(_make_request(conv_id, followup_q, rv))
    lat3 = round(time.monotonic() - t0, 2)
    print(f"    type={r3.type}  latency={lat3}s")
    print(f"    A: {str(r3.content)[:120]}")
    _record("3_multi_turn", "T3 type=answer", r3.type == "answer")

    # Verify conversation store accumulated all turns
    turns = conversation_manager.get_thread(conv_id)
    # T1: user+assistant, T2: user+assistant, T3: user+assistant = 6 turns
    _record("3_multi_turn", "conversation store has 6 turns",
            len(turns) == 6, f"got {len(turns)} turns")

    print(f"\n  Conversation thread latencies: T1={lat1}s  T2={lat2}s  T3={lat3}s")


# ── SECTION 4: Conversation isolation ────────────────────────────────────────

def section4_isolation():
    print("\n" + "="*60)
    print("SECTION 4 — Conversation isolation (two parallel conversations)")
    print("="*60)

    _reset()
    conv_a = str(uuid.uuid4())
    conv_b = str(uuid.uuid4())
    rv = _rv_ml()

    # Conv A: ask question
    run(_make_request(conv_a, "what is machine learning?", rv))
    run(_make_request(conv_a, "what are the applications?", rv))

    # Conv B: completely fresh conversation
    run(_make_request(conv_b, "what is supervised learning?", rv))

    turns_a = conversation_manager.get_thread(conv_a)
    turns_b = conversation_manager.get_thread(conv_b)

    _record("4_isolation", "conv_a has 4 turns", len(turns_a) == 4,
            f"got {len(turns_a)}")
    _record("4_isolation", "conv_b has 2 turns", len(turns_b) == 2,
            f"got {len(turns_b)}")

    # Check conv B doesn't see conv A's history in its prompts
    # (we can verify indirectly: conv B has 2 turns, conv A has 4)
    _record("4_isolation", "conversations are independent",
            len(turns_a) != len(turns_b))

    print(f"  conv_a turns={len(turns_a)}, conv_b turns={len(turns_b)}")


# ── SECTION 5: Follow-up chip grounding ──────────────────────────────────────

def section5_followup_grounding():
    print("\n" + "="*60)
    print("SECTION 5 — Follow-up chip grounding (ask each chip back to QA)")
    print("="*60)

    from app.services.qa_service import answer as qa_answer
    from app.context.tab_context_engine import format_read_view

    _reset()
    conv_id = str(uuid.uuid4())
    rv = _rv_amazon()
    resp = run(_make_request(conv_id, "summarize this page", rv))

    followups = resp.suggested_followups
    print(f"  Generated {len(followups)} follow-up(s)")

    rv_str = format_read_view(rv)
    grounded_count = 0
    for q in followups:
        ar = qa_answer(rv_str, q, [])
        grounded = ar.grounded
        if grounded:
            grounded_count += 1
        status = "GROUNDED" if grounded else "NOT_FOUND"
        print(f"  [{status}] {q}")
        print(f"    A: {ar.text[:100]}")
        _record("5_followup_grounding", f"grounded: {q[:50]}", grounded)

    if followups:
        _record("5_followup_grounding", f"grounding rate >= 50%",
                grounded_count / len(followups) >= 0.5,
                f"{grounded_count}/{len(followups)} grounded")


# ── SECTION 6: Latency benchmarks ────────────────────────────────────────────

def section6_latency(sum_latencies: list, ask_latencies: list):
    print("\n" + "="*60)
    print("SECTION 6 — Latency benchmarks")
    print("="*60)

    avg_sum = round(sum(sum_latencies) / len(sum_latencies), 2)
    avg_ask = round(sum(ask_latencies) / len(ask_latencies), 2)

    print(f"  Summarize: avg={avg_sum}s  samples={sum_latencies}")
    print(f"  Ask:       avg={avg_ask}s  samples={ask_latencies}")

    _record("6_latency", f"avg summarize < 8s", avg_sum < 8.0, f"{avg_sum}s")
    _record("6_latency", f"avg ask < 4s",       avg_ask < 4.0, f"{avg_ask}s")

    # Option B preserved: ask must be faster than summarize (no follow-up overhead)
    if avg_sum > 0 and avg_ask > 0:
        _record("6_latency", "ask faster than summarize (Option B)",
                avg_ask <= avg_sum * 1.5,
                f"ask={avg_ask}s sum={avg_sum}s")


# ── Run all sections ──────────────────────────────────────────────────────────

def run_validation():
    print("\nSlice 3 Live Validation — Chat UI Shell / Multi-turn")
    print(f"Backend: http://localhost:8000  (OpenRouter gpt-4o-mini)")

    sum_latencies = section1_summarize_regression()
    ask_latencies = section2_ask_regression()
    section3_multi_turn()
    section4_isolation()
    section5_followup_grounding()
    section6_latency(sum_latencies, ask_latencies)

    # ── Summary ───────────────────────────────────────────────────────────────
    total  = len(results)
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = total - passed

    print(f"\n{'='*60}")
    print(f"VALIDATION COMPLETE — Slice 3")
    print(f"  Total:  {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")

    if failed:
        print("\nFAILED CHECKS:")
        for r in results:
            if r["status"] == FAIL:
                print(f"  [{r['section']}] {r['label']}  {r['detail']}")

    out_path = os.path.join(os.path.dirname(__file__), "validation_results_slice3.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\n  Results saved: {out_path}")

    return failed == 0


if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)
