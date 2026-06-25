"""
V2.5 Slice 2 — Live Validation Script
Tests Q&A across 5 page types, follow-up turns, hallucination probes,
and the page-change scenario.
Provider: OpenRouter / gpt-4o-mini (from .env)
"""
import io, json, sys, time, uuid, os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
os.chdir(os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(__file__))

from app.schemas.assist import ReadView, AssistRequest
from app.assist.ambient_assistant import run
from app.conversation import manager as conversation_manager

# ── Page fixtures (same ReadViews as Slice 1 validation) ─────────────────────

def _rv_wikipedia():
    return ReadView(
        url="https://en.wikipedia.org/wiki/Machine_learning",
        title="Machine learning - Wikipedia",
        headings=["Machine learning", "Overview", "Supervised learning",
                  "Unsupervised learning", "Reinforcement learning", "Applications", "Limitations", "Bias"],
        content_blocks=[
            {"selector": "p:1", "text": "Machine learning (ML) is a field of study in artificial intelligence concerned with the development and study of statistical algorithms that can learn from data and generalize to unseen data."},
            {"selector": "p:2", "text": "Supervised learning algorithms build a mathematical model of a set of data that contains both the inputs and the desired outputs, known as training data."},
            {"selector": "p:3", "text": "Unsupervised learning algorithms find structures in data that has not been labelled, classified or categorized."},
            {"selector": "p:4", "text": "Reinforcement learning is an area of machine learning concerned with how software agents ought to take actions in an environment in order to maximize the notion of cumulative reward."},
            {"selector": "p:5", "text": "Applications include computer vision, natural language processing, credit-card fraud detection, medical diagnosis, and climate science."},
            {"selector": "p:6", "text": "Limitations: small training data, overfitting, poor interpretability. Bias is a major concern when the training data does not represent the target population."},
        ],
        visible_text=(
            "Machine learning (ML) is a field of artificial intelligence. "
            "Supervised learning uses labelled training data. "
            "Unsupervised learning finds structure in unlabelled data. "
            "Reinforcement learning maximises cumulative reward. "
            "Applications: computer vision, NLP, fraud detection, medical diagnosis. "
            "Limitations: overfitting, interpretability, data bias."
        ),
        metadata={"description": "Machine learning Wikipedia overview"},
    )

def _rv_github():
    return ReadView(
        url="https://github.com/tiangolo/fastapi",
        title="tiangolo/fastapi: FastAPI framework, high performance, easy to learn",
        headings=["FastAPI", "Requirements", "Installation", "Example", "Performance"],
        content_blocks=[
            {"selector": ".readme p:1", "text": "FastAPI is a modern, fast (high-performance), web framework for building APIs with Python based on standard Python type hints."},
            {"selector": ".readme p:2", "text": "Key features: Fast — very high performance, on par with NodeJS and Go (thanks to Starlette and Pydantic). Fast to code — increase the speed to develop features by about 200% to 300%."},
            {"selector": ".stars", "text": "75,400 stars · 6,400 forks · MIT License · Python 3.8+"},
            {"selector": ".install", "text": "pip install fastapi"},
        ],
        visible_text=(
            "FastAPI is a modern, fast web framework for building APIs with Python.\n"
            "Key features: high performance (par with NodeJS/Go), 200-300% faster dev, "
            "40% fewer bugs, automatic interactive API docs.\n"
            "75,400 stars. MIT License. Python 3.8+.\n"
            "Install: pip install fastapi"
        ),
        metadata={"description": "FastAPI Python framework"},
    )

def _rv_news():
    return ReadView(
        url="https://www.theverge.com/2024/5/14/google-openai-ai-competition",
        title="The AI arms race between Google and OpenAI is heating up - The Verge",
        headings=["The AI arms race", "OpenAI moved first", "Google responded at I/O", "What it means"],
        content_blocks=[
            {"selector": "article p:1", "text": "The rivalry between Google and OpenAI escalated dramatically this week as both companies announced major updates to their flagship AI models."},
            {"selector": "article p:2", "text": "OpenAI unveiled GPT-4o, a multimodal model that can see, hear, and respond in real time with latency as low as 232ms."},
            {"selector": "article p:3", "text": "Google announced Gemini 1.5 Pro with a 2 million token context window and showcased Project Astra, a prototype universal AI agent."},
            {"selector": ".byline", "text": "By Nilay Patel · May 14, 2024 · 4 min read"},
        ],
        visible_text=(
            "The rivalry between Google and OpenAI escalated dramatically this week. "
            "OpenAI unveiled GPT-4o with 232ms latency. "
            "Google announced Gemini 1.5 Pro with 2M token context and Project Astra. "
            "By Nilay Patel · May 14, 2024 · 4 min read"
        ),
        metadata={"description": "AI arms race article", "og:site_name": "The Verge"},
    )

def _rv_amazon():
    return ReadView(
        url="https://www.amazon.com/dp/B0BSHF7LLL",
        title="Apple MacBook Pro 14-inch with M3 Pro chip — $1,799.00",
        content_blocks=[
            {"selector": "#productTitle", "text": "Apple MacBook Pro 14-inch Laptop with M3 Pro chip"},
            {"selector": "#price", "text": "$1,799.00"},
            {"selector": ".feature-1", "text": "M3 Pro chip: 11-core CPU, 14-core GPU"},
            {"selector": ".feature-2", "text": "Up to 18 hours of battery life"},
            {"selector": ".feature-3", "text": "14.2-inch Liquid Retina XDR display, 120Hz ProMotion"},
            {"selector": ".rating", "text": "4.7 out of 5 stars · 2,341 ratings"},
            {"selector": ".shipping", "text": "In stock. Free delivery on eligible orders. Ships from Amazon.com."},
        ],
        visible_text=(
            "Apple MacBook Pro 14-inch with M3 Pro chip.\n"
            "Price: $1,799.00\n"
            "Rating: 4.7/5 (2,341 ratings)\n"
            "M3 Pro: 11-core CPU, 14-core GPU\n"
            "18 hours battery life\n"
            "14.2-inch Liquid Retina XDR, 120Hz ProMotion\n"
            "In stock. Ships from Amazon."
        ),
        metadata={"description": "MacBook Pro 14 M3 Pro Amazon"},
    )

def _rv_blog():
    return ReadView(
        url="https://kentcdodds.com/blog/fix-the-slow-render-before-you-fix-the-re-render",
        title="Fix the slow render before you fix the re-render | Kent C. Dodds",
        headings=["Fix the slow render", "The common mistake", "Measuring is everything",
                  "Common causes", "What about memo?", "Conclusion"],
        content_blocks=[
            {"selector": "article p:1", "text": "One of the most common mistakes React developers make is to try to fix a performance problem by memoizing components before actually measuring what is happening."},
            {"selector": "article p:2", "text": "If a component renders once but takes 500ms, it will still make your app feel terrible no matter how few re-renders it does."},
            {"selector": "article p:3", "text": "Before reaching for React.memo, open the React DevTools Profiler. Record a user interaction. Look at the flame graph. Find what is actually slow."},
            {"selector": "article p:4", "text": "Common causes of slow renders: expensive computations in render, large DOM trees, missing key props, synchronous data fetching, heavy third-party libraries."},
            {"selector": "article p:5", "text": "React.memo is not free — it adds overhead on every parent render for the props comparison. If your component is already fast, memoization makes it slower."},
            {"selector": "article p:6", "text": "The rule: profile first, fix the component render, then reduce re-renders with memo. Never skip to step 3."},
            {"selector": ".byline", "text": "Kent C. Dodds · April 2023 · 8 min read"},
        ],
        visible_text=(
            "Common mistake: using memoization without measuring performance first. "
            "A component that renders once but takes 500ms still makes the app feel slow. "
            "Use React DevTools Profiler first. Record, look at the flame graph. "
            "Causes: expensive computations, large DOM trees, missing key props. "
            "React.memo adds overhead. Only memoize with measured benefit. "
            "Rule: profile -> fix render -> reduce re-renders. Kent C. Dodds · April 2023"
        ),
        metadata={"author": "Kent C. Dodds", "og:type": "article"},
    )


# ── Test scenarios ─────────────────────────────────────────────────────────────

SCENARIOS = [
    # (label, read_view_fn, question)
    ("wikipedia_what_is_ml",        _rv_wikipedia, "What is machine learning?"),
    ("wikipedia_types_of_learning",  _rv_wikipedia, "What are the three main types of machine learning?"),
    ("github_install",               _rv_github,    "How do I install FastAPI?"),
    ("github_stars",                 _rv_github,    "How many stars does this repo have?"),
    ("news_what_happened",           _rv_news,      "What did OpenAI announce?"),
    ("news_author",                  _rv_news,      "Who wrote this article?"),
    ("amazon_price",                 _rv_amazon,    "What is the price?"),
    ("amazon_battery",               _rv_amazon,    "How long does the battery last?"),
    ("blog_main_argument",           _rv_blog,      "What is the main argument of this article?"),
    ("blog_how_to_profile",          _rv_blog,      "How do I profile my React app?"),
]

HALLUCINATION_PROBES = [
    ("wiki_unanswerable_price",   _rv_wikipedia, "What is the price of this product?"),
    ("wiki_unanswerable_author",  _rv_wikipedia, "Who is the CEO of the company?"),
    ("github_unanswerable_phone", _rv_github,    "What is the author's phone number?"),
    ("blog_unanswerable_year",    _rv_blog,      "When was Kent born?"),
    ("amazon_unanswerable_color_blue", _rv_amazon, "Is this available in blue?"),
]


def run_single(label: str, rv: ReadView, question: str, conv_id: str | None = None) -> dict:
    cid = conv_id or str(uuid.uuid4())
    request = AssistRequest(
        conversation_id=cid,
        message=question,
        read_view=rv,
        context_fingerprint=f"{rv.url[:40]}|{rv.title[:40]}",
        selection_scope="page",
    )
    t0 = time.monotonic()
    try:
        resp = run(request)
        elapsed = time.monotonic() - t0
        return {
            "status": "ok",
            "label": label,
            "question": question,
            "intent": resp.intent,
            "routed_to": resp.routed_to,
            "type": resp.type,
            "answer": resp.content if isinstance(resp.content, str) else str(resp.content),
            "latency_s": round(elapsed, 2),
            "context_chars": resp.meta.context_chars,
            "conversation_id": cid,
        }
    except Exception as exc:
        elapsed = time.monotonic() - t0
        return {"status": "error", "label": label, "error": str(exc), "latency_s": round(elapsed, 2)}


def run_validation():
    conversation_manager._reset_store_for_testing()
    all_results = {}

    # ── 1. Single-question Q&A per page type ─────────────────────────────────
    print("\n" + "="*60)
    print("SECTION 1 — Per-page Q&A (single turn)")
    print("="*60)
    for label, rv_fn, question in SCENARIOS:
        rv = rv_fn()
        r = run_single(label, rv, question)
        all_results[label] = r
        status = "OK" if r["status"] == "ok" else "ERR"
        ans_preview = r.get("answer", r.get("error", ""))[:100]
        print(f"\n[{status}] {label}")
        print(f"  Q: {question}")
        print(f"  A: {ans_preview}")
        print(f"  intent={r.get('intent')} routed={r.get('routed_to')} latency={r.get('latency_s')}s ctx={r.get('context_chars')}")

    # ── 2. Hallucination probes ───────────────────────────────────────────────
    print("\n" + "="*60)
    print("SECTION 2 — Hallucination probes (unanswerable questions)")
    print("="*60)
    for label, rv_fn, question in HALLUCINATION_PROBES:
        rv = rv_fn()
        r = run_single(label, rv, question)
        all_results[label] = r
        answer = r.get("answer", "")
        not_found_exact = "I don't see that on this page." in answer
        print(f"\n[{'GROUNDED' if not_found_exact else 'CHECK'}] {label}")
        print(f"  Q: {question}")
        print(f"  A: {answer[:150]}")
        print(f"  exact_not_found={not_found_exact}  latency={r.get('latency_s')}s")

    # ── 3. Multi-turn follow-up ───────────────────────────────────────────────
    print("\n" + "="*60)
    print("SECTION 3 — Multi-turn follow-up questions")
    print("="*60)
    conv_id = str(uuid.uuid4())
    rv = _rv_blog()
    turns = [
        ("blog_turn1_argument",  "What is the main argument?"),
        ("blog_turn2_followup",  "What tool should I use first?"),
        ("blog_turn3_deepdive",  "What are the common causes of slow renders they mention?"),
    ]
    for label, question in turns:
        r = run_single(label, rv, question, conv_id=conv_id)
        all_results[label] = r
        print(f"\n[TURN] {label}")
        print(f"  Q: {question}")
        print(f"  A: {r.get('answer', r.get('error',''))[:150]}")
        print(f"  latency={r.get('latency_s')}s")

    # ── 4. Post-summary follow-up (summarize then ask) ────────────────────────
    print("\n" + "="*60)
    print("SECTION 4 — Ask follow-up after summary (cross-intent history)")
    print("="*60)
    conv_id = str(uuid.uuid4())
    rv = _rv_amazon()
    # Step 1: summarize
    sum_req = AssistRequest(
        conversation_id=conv_id, message="summarize this page",
        read_view=rv, context_fingerprint="amz-fp", selection_scope="page",
    )
    t0 = time.monotonic()
    sum_resp = run(sum_req)
    sum_latency = round(time.monotonic() - t0, 2)
    sum_tldr = sum_resp.content.tldr if hasattr(sum_resp.content, "tldr") else str(sum_resp.content)
    print(f"\n[SUMMARY] amazon_summary_then_ask — summary done ({sum_latency}s)")
    print(f"  TL;DR: {sum_tldr[:100]}")

    # Step 2: ask follow-up — avoid "summary" keyword (triggers _SUMMARIZE classifier)
    ask_q = "What is the customer rating for this product?"
    r = run_single("amazon_ask_after_summary", rv, ask_q, conv_id=conv_id)
    all_results["amazon_ask_after_summary"] = r
    print(f"\n[Q&A]  amazon_ask_after_summary")
    print(f"  Q: {ask_q}")
    print(f"  A: {r.get('answer','')[:150]}")
    print(f"  intent={r.get('intent')} latency={r.get('latency_s')}s")

    # ── 5. Page change scenario ───────────────────────────────────────────────
    print("\n" + "="*60)
    print("SECTION 5 — Page change between questions (same conversation)")
    print("="*60)
    conv_id = str(uuid.uuid4())

    # Ask on Wikipedia ML page
    r1 = run_single("page_change_q1_ml", _rv_wikipedia(), "What is supervised learning?", conv_id=conv_id)
    print(f"\n[PAGE 1 — Wikipedia ML]")
    print(f"  Q: What is supervised learning?")
    print(f"  A: {r1.get('answer','')[:150]}")

    # Now switch to FastAPI GitHub page with SAME conversation_id
    r2 = run_single("page_change_q2_github", _rv_github(), "What is the price of this product?", conv_id=conv_id)
    all_results["page_change_q1_ml"] = r1
    all_results["page_change_q2_github"] = r2
    ans2 = r2.get("answer", "")
    anchored_to_github = "fastapi" in ans2.lower() or "I don't see that on this page." in ans2
    anchored_to_ml = "supervised" in ans2.lower() or "machine learning" in ans2.lower()
    print(f"\n[PAGE 2 — GitHub FastAPI (same conv_id)]")
    print(f"  Q: What is the price of this product?")
    print(f"  A: {ans2[:150]}")
    print(f"  anchored_to_new_page={anchored_to_github}  leaked_prior_page={anchored_to_ml}")

    # ── Write results ─────────────────────────────────────────────────────────
    out_path = os.path.join(os.path.dirname(__file__), "validation_results_slice2.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, default=str)

    # ── Summary stats ─────────────────────────────────────────────────────────
    ok = [v for v in all_results.values() if v.get("status") == "ok"]
    err = [v for v in all_results.values() if v.get("status") == "error"]
    latencies = [v["latency_s"] for v in ok]
    avg_lat = round(sum(latencies) / len(latencies), 2) if latencies else 0

    print(f"\n\n{'='*60}")
    print(f"VALIDATION COMPLETE")
    print(f"  Total: {len(all_results)} scenarios")
    print(f"  OK:    {len(ok)}")
    print(f"  Error: {len(err)}")
    print(f"  Avg latency: {avg_lat}s  Min: {min(latencies):.2f}s  Max: {max(latencies):.2f}s")
    print(f"  Full results: {out_path}")

    return all_results


if __name__ == "__main__":
    run_validation()
