"""
BUG-05 Live Validation — Suggested Follow-up Questions
Measures: follow-up usefulness, grounding quality, trigger-word safety, latency impact.
Provider: OpenRouter / gpt-4o-mini (from .env)
"""
import io, json, sys, time, uuid, os
from unittest.mock import patch

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

from app.schemas.assist import ReadView, AssistRequest
from app.assist.ambient_assistant import run
from app.services import followup_service as _fup_svc
from app.conversation import manager as conversation_manager
from app.intent.router import classify

# ── Re-use same ReadView fixtures as Slice 1 / 2 ──────────────────────────────

def _rv_wikipedia():
    return ReadView(
        url="https://en.wikipedia.org/wiki/Machine_learning",
        title="Machine learning - Wikipedia",
        headings=["Machine learning", "Overview", "Supervised learning",
                  "Unsupervised learning", "Reinforcement learning", "Applications"],
        content_blocks=[
            {"selector": "p:1", "text": "Machine learning (ML) is a field of artificial intelligence."},
            {"selector": "p:2", "text": "Supervised learning algorithms build a model from labelled training data."},
            {"selector": "p:3", "text": "Unsupervised learning finds structure in unlabelled data."},
            {"selector": "p:4", "text": "Reinforcement learning maximises cumulative reward."},
            {"selector": "p:5", "text": "Applications: computer vision, NLP, fraud detection, medical diagnosis."},
            {"selector": "p:6", "text": "Limitations: overfitting, interpretability, data bias."},
        ],
        visible_text=(
            "Machine learning (ML) is a field of artificial intelligence. "
            "Supervised learning uses labelled training data. "
            "Unsupervised learning finds structure in unlabelled data. "
            "Reinforcement learning maximises cumulative reward. "
            "Applications: computer vision, NLP, fraud detection, medical diagnosis. "
            "Limitations: overfitting, interpretability, data bias."
        ),
        metadata={"description": "Machine learning Wikipedia"},
    )

def _rv_github():
    return ReadView(
        url="https://github.com/tiangolo/fastapi",
        title="tiangolo/fastapi: FastAPI framework",
        headings=["FastAPI", "Requirements", "Installation", "Example", "Performance"],
        content_blocks=[
            {"selector": ".readme p:1", "text": "FastAPI is a modern, fast web framework for building APIs with Python."},
            {"selector": ".readme p:2", "text": "Key features: high performance, 200-300% faster dev, 40% fewer bugs, automatic docs."},
            {"selector": ".stars", "text": "75,400 stars · MIT License · Python 3.8+"},
            {"selector": ".install", "text": "pip install fastapi"},
        ],
        visible_text=(
            "FastAPI is a modern, fast web framework for building APIs with Python.\n"
            "Key features: high performance (par with NodeJS/Go), 200-300% faster dev, 40% fewer bugs.\n"
            "75,400 stars. MIT License. Python 3.8+.\nInstall: pip install fastapi"
        ),
        metadata={"description": "FastAPI Python framework"},
    )

def _rv_news():
    return ReadView(
        url="https://www.theverge.com/2024/5/14/google-openai-ai-competition",
        title="The AI arms race between Google and OpenAI - The Verge",
        headings=["The AI arms race", "OpenAI moved first", "Google responded", "What it means"],
        content_blocks=[
            {"selector": "article p:1", "text": "The rivalry between Google and OpenAI escalated dramatically this week."},
            {"selector": "article p:2", "text": "OpenAI unveiled GPT-4o with 232ms latency real-time multimodal capability."},
            {"selector": "article p:3", "text": "Google announced Gemini 1.5 Pro with 2M token context and Project Astra."},
            {"selector": ".byline", "text": "By Nilay Patel · May 14, 2024 · 4 min read"},
        ],
        visible_text=(
            "Rivalry between Google and OpenAI escalated. "
            "OpenAI unveiled GPT-4o with 232ms latency. "
            "Google announced Gemini 1.5 Pro with 2M token context and Project Astra. "
            "By Nilay Patel · May 14, 2024."
        ),
        metadata={"og:site_name": "The Verge"},
    )

def _rv_amazon():
    return ReadView(
        url="https://www.amazon.com/dp/B0BSHF7LLL",
        title="Apple MacBook Pro 14-inch M3 Pro — $1,799.00",
        content_blocks=[
            {"selector": "#productTitle", "text": "Apple MacBook Pro 14-inch with M3 Pro chip"},
            {"selector": "#price", "text": "$1,799.00"},
            {"selector": ".feature-1", "text": "M3 Pro chip: 11-core CPU, 14-core GPU"},
            {"selector": ".feature-2", "text": "Up to 18 hours battery life"},
            {"selector": ".feature-3", "text": "14.2-inch Liquid Retina XDR, 120Hz ProMotion"},
            {"selector": ".rating", "text": "4.7 out of 5 stars · 2,341 ratings"},
            {"selector": ".shipping", "text": "In stock. Free delivery. Ships from Amazon."},
        ],
        visible_text=(
            "Apple MacBook Pro 14-inch with M3 Pro chip.\n"
            "Price: $1,799.00\nRating: 4.7/5 (2,341 ratings)\n"
            "M3 Pro: 11-core CPU, 14-core GPU\n18 hours battery\n"
            "14.2-inch Liquid Retina XDR 120Hz\nIn stock. Ships from Amazon."
        ),
        metadata={},
    )

def _rv_blog():
    return ReadView(
        url="https://kentcdodds.com/blog/fix-the-slow-render-before-you-fix-the-re-render",
        title="Fix the slow render before the re-render | Kent C. Dodds",
        headings=["Fix the slow render", "Common mistake", "Measuring", "Causes", "memo?"],
        content_blocks=[
            {"selector": "article p:1", "text": "Common mistake: memoizing before measuring."},
            {"selector": "article p:2", "text": "A component that renders once but takes 500ms still feels slow."},
            {"selector": "article p:3", "text": "Use React DevTools Profiler first. Record, look at the flame graph."},
            {"selector": "article p:4", "text": "Causes: expensive computations, large DOM trees, missing key props, heavy libraries."},
            {"selector": "article p:5", "text": "React.memo adds overhead on every parent render."},
            {"selector": "article p:6", "text": "Rule: profile first, fix the component, then reduce re-renders."},
        ],
        visible_text=(
            "Common mistake: memoizing before measuring. "
            "500ms render is slow regardless of re-render count. "
            "Use React DevTools Profiler. Record, look at flame graph. "
            "Causes: expensive computations, large DOM, missing keys, heavy libraries. "
            "React.memo adds overhead. Profile first, fix render, then reduce re-renders. "
            "Kent C. Dodds · April 2023."
        ),
        metadata={"author": "Kent C. Dodds"},
    )


PAGE_FIXTURES = [
    ("wikipedia", _rv_wikipedia),
    ("github",    _rv_github),
    ("news",      _rv_news),
    ("amazon",    _rv_amazon),
    ("blog",      _rv_blog),
]

TRIGGER_WORDS = frozenset({
    "summarize", "summarise", "summary", "tl;dr", "tldr", "brief", "overview", "recap", "condense",
    "research", "look up", "look into", "investigate", "find info", "find information",
    "compare", "comparison", "versus", " vs ", "which is better", "which is worse",
    "difference between",
})


def _has_trigger(question: str) -> bool:
    lowered = question.lower()
    return any(tw in lowered for tw in TRIGGER_WORDS)


def _would_be_misrouted(question: str) -> bool:
    r = classify(question)
    return r.intent not in ("ask", "unknown")


def _run_scenario(label: str, rv: ReadView, message: str) -> dict:
    conversation_manager._reset_store_for_testing()
    req = AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message=message,
        read_view=rv,
        context_fingerprint=f"{rv.url[:40]}",
        selection_scope="page",
    )
    t0 = time.monotonic()
    resp = run(req)
    total_s = round(time.monotonic() - t0, 2)
    followups = resp.suggested_followups or []
    return {
        "label": label,
        "intent": resp.intent,
        "message": message,
        "followups": followups,
        "count": len(followups),
        "total_latency_s": total_s,
        "latency_ms": resp.meta.latency_ms,
        "context_chars": resp.meta.context_chars,
        "trigger_flags": [q for q in followups if _has_trigger(q)],
        "misrouted": [q for q in followups if _would_be_misrouted(q)],
    }


def run_validation():
    all_results: dict[str, dict] = {}

    # ── 1. Follow-ups after SUMMARIZE ─────────────────────────────────────────
    print("\n" + "="*60)
    print("SECTION 1 — Follow-ups after SUMMARIZE (5 page types)")
    print("="*60)

    for name, rv_fn in PAGE_FIXTURES:
        label = f"sum_{name}"
        r = _run_scenario(label, rv_fn(), "summarize this page")
        all_results[label] = r
        print(f"\n[{label}] latency={r['total_latency_s']}s  count={r['count']}")
        for i, q in enumerate(r["followups"], 1):
            flag = " [TRIGGER]" if _has_trigger(q) else ""
            misroute = f" [MISROUTED→{classify(q).intent}]" if _would_be_misrouted(q) else ""
            print(f"  Q{i}: {q}{flag}{misroute}")
        if not r["followups"]:
            print("  (no follow-ups generated)")

    # ── 2. Follow-ups after ASK ────────────────────────────────────────────────
    print("\n" + "="*60)
    print("SECTION 2 — Follow-ups after ASK (5 page types)")
    print("="*60)

    ask_questions = {
        "wikipedia": "What is machine learning?",
        "github":    "How do I install this framework?",
        "news":      "What did OpenAI announce?",
        "amazon":    "What is the price?",
        "blog":      "What is the main argument?",
    }

    for name, rv_fn in PAGE_FIXTURES:
        label = f"ask_{name}"
        r = _run_scenario(label, rv_fn(), ask_questions[name])
        all_results[label] = r
        print(f"\n[{label}] Q: {ask_questions[name]}")
        print(f"  latency={r['total_latency_s']}s  count={r['count']}")
        for i, q in enumerate(r["followups"], 1):
            flag = " [TRIGGER]" if _has_trigger(q) else ""
            misroute = f" [MISROUTED→{classify(q).intent}]" if _would_be_misrouted(q) else ""
            print(f"  FU{i}: {q}{flag}{misroute}")

    # ── 3. Latency isolation: time followup_service.generate() directly ──────────
    print("\n" + "="*60)
    print("SECTION 3 — Latency decomposition (follow-up call timed in isolation)")
    print("  meta.latency_ms = total wall-clock (primary + follow-up)")
    print("  followup_ms = followup_service.generate() timed standalone")
    print("="*60)

    from app.context.tab_context_engine import format_read_view as _fmt
    followup_latencies: dict[str, int] = {}
    for name, rv_fn in PAGE_FIXTURES:
        rv = rv_fn()
        rv_str = _fmt(rv)
        t_fu = time.monotonic()
        _fup_svc.generate(rv_str, f"User asked: What is this page about?\nAssistant answered: This page covers {rv.title}.")
        followup_latencies[name] = int((time.monotonic() - t_fu) * 1000)

    for name, rv_fn in PAGE_FIXTURES:
        sum_label = f"sum_{name}"
        ask_label = f"ask_{name}"
        total_sum = all_results[sum_label]["latency_ms"]
        total_ask = all_results[ask_label]["latency_ms"]
        fu_ms     = followup_latencies[name]
        primary_sum = total_sum - fu_ms
        primary_ask = total_ask - fu_ms
        print(f"  {name:12s}  followup≈{fu_ms:4d}ms  |"
              f"  summarize: primary≈{primary_sum:4d}ms  total={total_sum:4d}ms  |"
              f"  ask: primary≈{primary_ask:4d}ms  total={total_ask:4d}ms")

    # ── 4. Grounding check: do follow-ups pass the QA grounding test? ──────────
    print("\n" + "="*60)
    print("SECTION 4 — Grounding check (ask each follow-up back to the QA engine)")
    print("="*60)

    from app.services.qa_service import answer as qa_answer
    from app.context.tab_context_engine import format_read_view

    grounding_results: list[dict] = []
    for name, rv_fn in PAGE_FIXTURES:
        label = f"sum_{name}"
        r = all_results.get(label, {})
        rv = rv_fn()
        rv_str = format_read_view(rv)
        for q in r.get("followups", []):
            t0 = time.monotonic()
            ar = qa_answer(rv_str, q, [])
            grounding_s = round(time.monotonic() - t0, 2)
            grounding_results.append({
                "page": name, "question": q,
                "grounded": ar.grounded, "answer_preview": ar.text[:100],
                "latency_s": grounding_s,
            })
            status = "GROUNDED" if ar.grounded else "NOT_FOUND"
            print(f"\n  [{status}] {name}: {q}")
            print(f"    A: {ar.text[:100]}")

    # ── 5. Trigger-word safety summary ────────────────────────────────────────
    all_followups = []
    for r in all_results.values():
        all_followups.extend(r.get("followups", []))

    triggered  = [q for q in all_followups if _has_trigger(q)]
    misrouted  = [q for q in all_followups if _would_be_misrouted(q)]
    grounded_n = sum(1 for g in grounding_results if g["grounded"])
    total_fup  = len(all_followups)

    # ── Write results ──────────────────────────────────────────────────────────
    out = {
        "scenarios": all_results,
        "grounding_checks": grounding_results,
        "summary": {
            "total_followups": total_fup,
            "trigger_flagged": len(triggered),
            "misrouted": len(misrouted),
            "grounded": grounded_n,
            "not_found": len(grounding_results) - grounded_n,
        },
    }
    out_path = os.path.join(os.path.dirname(__file__), "validation_results_bug05.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)

    latencies_total = [r["latency_ms"] / 1000 for r in all_results.values()]
    fu_ms_values    = list(followup_latencies.values())
    avg_fu_ms       = round(sum(fu_ms_values) / len(fu_ms_values))
    avg_total_s     = round(sum(latencies_total) / len(latencies_total), 2)

    print(f"\n\n{'='*60}")
    print("VALIDATION COMPLETE — BUG-05")
    print(f"  Scenarios:             {len(all_results)}")
    print(f"  Total follow-ups:      {total_fup}")
    print(f"  Trigger-flagged:       {len(triggered)}")
    print(f"  Misrouted:             {len(misrouted)}")
    print(f"  Grounding checks:      {len(grounding_results)}")
    print(f"  Grounded (answerable): {grounded_n}/{len(grounding_results)}")
    print(f"  Avg total latency:     {avg_total_s}s (primary + follow-up)")
    print(f"  Avg follow-up overhead: ~{avg_fu_ms}ms (~{round(avg_fu_ms/avg_total_s/10, 0)}% of total)")
    print(f"  Results: {out_path}")

    return out


if __name__ == "__main__":
    run_validation()
