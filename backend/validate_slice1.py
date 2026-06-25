"""
V2.5 Slice 1 — Live Validation Script
Calls ambient_assistant.run() directly (no FastAPI server / DB needed).
Provider: whatever is configured in .env (currently OpenRouter/gpt-4o-mini).
"""

import json
import sys
import time
import uuid
import os
import io

# Force UTF-8 stdout on Windows (avoids cp1252 errors for arrows, bullets, etc.)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Make sure we're running from the backend/ directory so imports resolve
os.chdir(os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(__file__))

from app.schemas.assist import ReadView, AssistRequest
from app.assist.ambient_assistant import run


# ── Realistic page fixtures ────────────────────────────────────────────────────

PAGES = {

    "wikipedia_machine_learning": AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message="summarize this page",
        read_view=ReadView(
            url="https://en.wikipedia.org/wiki/Machine_learning",
            title="Machine learning - Wikipedia",
            headings=[
                "Machine learning",
                "Overview",
                "History and relationships to other fields",
                "Theory",
                "Approaches",
                "Supervised learning",
                "Unsupervised learning",
                "Reinforcement learning",
                "Feature learning",
                "Sparse dictionary learning",
                "Anomaly detection",
                "Applications",
                "Limitations",
                "Bias",
            ],
            content_blocks=[
                {"selector": "#mw-content-text p:nth-child(1)", "text": "Machine learning (ML) is a field of study in artificial intelligence concerned with the development and study of statistical algorithms that can learn from data and generalize to unseen data, and thus perform tasks without explicit instructions."},
                {"selector": "#mw-content-text p:nth-child(2)", "text": "Recently, generative artificial intelligence has become a notable application of ML. Artificial neural networks, inspired by the structure and function of biological neural networks, are used in many ML applications."},
                {"selector": "#mw-content-text p:nth-child(3)", "text": "ML is closely related to statistics, which focuses on prediction using algorithms rather than inference about populations. It is also related to data mining and optimization."},
                {"selector": ".mw-headline#Overview + p", "text": "As a scientific endeavour, machine learning grew out of the quest for artificial intelligence (AI). In the early days of AI, some researchers were interested in having machines learn from data."},
                {"selector": ".mw-headline#Supervised_learning + p", "text": "Supervised learning algorithms build a mathematical model of a set of data that contains both the inputs and the desired outputs. The data is known as training data. Each training example has one or more inputs and the desired output, also known as a supervisory signal."},
                {"selector": ".mw-headline#Unsupervised_learning + p", "text": "Unsupervised learning algorithms find structures in data that has not been labelled, classified or categorized. Instead of responding to feedback, unsupervised learning algorithms identify commonalities in the data and react based on the presence or absence of such commonalities in each new piece of data."},
                {"selector": ".mw-headline#Applications + p", "text": "There are many applications for machine learning, including: agriculture, anatomy, adaptive websites, affective computing, banking, bioinformatics, brain–machine interfaces, cheminformatics, citizen science, climate science, computer networks, computer vision, credit-card fraud detection, data quality, DNA sequence classification."},
                {"selector": ".mw-headline#Limitations + p", "text": "Although machine learning has been transformative in some fields, machine learning programs often fail to deliver expected results. Reasons for this include the small amount of training data available, overfitting, and poor interpretability of models."},
                {"selector": ".mw-headline#Bias + p", "text": "Machine learning approaches in particular can suffer from different data biases. A machine learning system trained specifically on current customers may not be able to predict the needs of new customer groups that are not represented in the training data."},
            ],
            visible_text=(
                "Machine learning (ML) is a field of study in artificial intelligence concerned with the development "
                "and study of statistical algorithms that can learn from data and generalize to unseen data. "
                "Recently, generative artificial intelligence has become a notable application of ML. "
                "Artificial neural networks are used in many ML applications.\n\n"
                "ML is closely related to statistics, which focuses on prediction using algorithms. "
                "Supervised learning algorithms build a mathematical model of a set of data that contains "
                "both the inputs and the desired outputs. "
                "Unsupervised learning algorithms find structures in data that has not been labelled, "
                "classified or categorized.\n\n"
                "Reinforcement learning is an area of machine learning concerned with how software agents "
                "ought to take actions in an environment in order to maximize the notion of cumulative reward.\n\n"
                "Applications include: computer vision, natural language processing, credit-card fraud detection, "
                "medical diagnosis, and climate science.\n\n"
                "Limitations: small training data, overfitting, poor interpretability. Bias is a major concern."
            ),
            metadata={"description": "Machine learning - Wikipedia overview article covering supervised, unsupervised, and reinforcement learning"},
        ),
        context_fingerprint="wp_ml_001",
        selection_scope="page",
    ),

    "github_repo_fastapi": AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message="give me a tldr",
        read_view=ReadView(
            url="https://github.com/tiangolo/fastapi",
            title="tiangolo/fastapi: FastAPI framework, high performance, easy to learn, fast to code, ready for production",
            headings=[
                "FastAPI",
                "Requirements",
                "Installation",
                "Example",
                "Run it",
                "Check it",
                "Interactive API docs",
                "Performance",
                "Dependencies",
                "License",
            ],
            content_blocks=[
                {"selector": ".markdown-body p:nth-child(1)", "text": "FastAPI is a modern, fast (high-performance), web framework for building APIs with Python based on standard Python type hints."},
                {"selector": ".markdown-body p:nth-child(2)", "text": "The key features are: Fast: Very high performance, on par with NodeJS and Go (thanks to Starlette and Pydantic). Fast to code: Increase the speed to develop features by about 200% to 300%. Fewer bugs: Reduce about 40% of human (developer) induced errors. Intuitive: Great editor support. Easy: Designed to be easy to use and learn. Short: Minimize code duplication."},
                {"selector": ".f4.my-3", "text": "FastAPI framework, high performance, easy to learn, fast to code, ready for production"},
                {"selector": "#readme .highlight pre", "text": "pip install fastapi"},
                {"selector": "#readme pre:nth-child(2)", "text": "from fastapi import FastAPI\napp = FastAPI()\n@app.get('/')\ndef read_root():\n    return {'Hello': 'World'}"},
                {"selector": ".BorderGrid-cell:nth-child(1)", "text": "75.4k stars · 6.4k forks · MIT License · Python"},
                {"selector": "#readme .requirements", "text": "Python 3.8+ and Starlette and Pydantic are required."},
                {"selector": "#readme .performance", "text": "Very high performance. Based on independent TechEmpower benchmarks, FastAPI is one of the fastest Python frameworks available."},
            ],
            visible_text=(
                "FastAPI is a modern, fast (high-performance), web framework for building APIs with Python "
                "based on standard Python type hints.\n\n"
                "Key features: Very high performance on par with NodeJS and Go (thanks to Starlette and Pydantic). "
                "Increase development speed by 200%-300%. Reduces about 40% of human-induced errors. "
                "Great editor support. Complete. Short. Robust. Standards-based.\n\n"
                "75,400 stars. 6,400 forks. MIT License. Python.\n\n"
                "Requirements: Python 3.8+\n"
                "Installation: pip install fastapi\n\n"
                "Example:\nfrom fastapi import FastAPI\napp = FastAPI()\n"
                "@app.get('/')\ndef read_root():\n    return {'Hello': 'World'}\n\n"
                "Run with: uvicorn main:app --reload\n"
                "Interactive API docs automatically generated at /docs (Swagger UI) and /redoc (ReDoc).\n\n"
                "Based on OpenAPI and JSON Schema standards. Used by Microsoft, Netflix, Uber."
            ),
            metadata={
                "description": "FastAPI framework, high performance, easy to learn, fast to code, ready for production",
                "og:type": "object",
            },
        ),
        context_fingerprint="gh_fastapi_001",
        selection_scope="page",
    ),

    "news_article_ai": AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message="brief overview please",
        read_view=ReadView(
            url="https://www.theverge.com/2024/5/14/24156744/google-openai-generative-ai-competition-io-gpt-4o",
            title="The AI arms race between Google and OpenAI is heating up - The Verge",
            headings=[
                "The AI arms race between Google and OpenAI is heating up",
                "OpenAI moved first with GPT-4o",
                "Google responded at I/O",
                "What it means for users",
                "The road ahead",
            ],
            content_blocks=[
                {"selector": "article p:nth-child(1)", "text": "The rivalry between Google and OpenAI escalated dramatically this week as both companies announced major updates to their flagship AI models, kicking off what analysts are calling the most competitive period in the history of consumer AI."},
                {"selector": "article p:nth-child(2)", "text": "OpenAI struck first on Monday, unveiling GPT-4o — a new multimodal model that can see, hear, and respond in real time. The model can engage in natural back-and-forth voice conversations, analyze emotions from facial expressions, and respond to its surroundings."},
                {"selector": "article p:nth-child(3)", "text": "Google fired back at its annual I/O developer conference on Tuesday, announcing Gemini 1.5 Pro would gain a context window of 2 million tokens — enough to process the entire text of War and Peace four times over. Google also showed off Project Astra, a prototype universal AI agent."},
                {"selector": "article p:nth-child(4)", "text": "Both companies are racing to make AI feel less like a tool and more like a collaborator. The demos were striking: an AI tutor that can see a student's homework and help guide them to solutions, a coding assistant that can debug problems in real time."},
                {"selector": "article .byline", "text": "By Nilay Patel and Verge Staff · May 14, 2024"},
                {"selector": "article .read-time", "text": "4 min read"},
            ],
            visible_text=(
                "The rivalry between Google and OpenAI escalated dramatically this week as both companies announced "
                "major updates to their flagship AI models, kicking off what analysts are calling the most competitive "
                "period in the history of consumer AI.\n\n"
                "OpenAI unveiled GPT-4o — a new multimodal model that can see, hear, and respond in real time. "
                "It can engage in natural voice conversations, analyze emotions, and respond to surroundings with "
                "latency as low as 232ms, matching human response times.\n\n"
                "Google responded at I/O with Gemini 1.5 Pro gaining a 2 million token context window. "
                "Project Astra was shown as a prototype universal AI agent that can describe its surroundings "
                "through a phone camera, read code, and have real-time conversations.\n\n"
                "Both companies are racing to make AI feel less like a tool and more like a collaborator. "
                "CEO Sam Altman called GPT-4o 'magic', while Google CEO Sundar Pichai called it an 'incredible' moment.\n\n"
                "What this means for users: Both GPT-4o and the new Gemini features will be available to free users, "
                "not just paid subscribers. The race to the bottom on pricing is accelerating.\n\n"
                "By Nilay Patel · May 14, 2024 · 4 min read"
            ),
            metadata={
                "description": "OpenAI and Google both unveiled major AI upgrades this week in a dramatic escalation of the AI arms race.",
                "article:published_time": "2024-05-14",
                "og:site_name": "The Verge",
            },
        ),
        context_fingerprint="verge_ai_race_001",
        selection_scope="page",
    ),

    "amazon_product_laptop": AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message="summarize",
        read_view=ReadView(
            url="https://www.amazon.com/dp/B0BSHF7LLL",
            title="Amazon.com: Apple MacBook Pro 14-inch Laptop with M3 Pro chip: Built for Apple Intelligence, 11-Core CPU, 14-Core GPU, 18GB Memory, 512GB, Space Black – $1,799.00",
            headings=[
                "Apple MacBook Pro 14-inch with M3 Pro chip",
                "About this item",
                "Technical Specifications",
                "Customer Reviews",
                "Frequently bought together",
            ],
            content_blocks=[
                {"selector": "#productTitle", "text": "Apple MacBook Pro 14-inch Laptop with M3 Pro chip: Built for Apple Intelligence, 11-Core CPU, 14-Core GPU, 18GB Memory, 512GB, Space Black"},
                {"selector": "#priceblock_ourprice", "text": "$1,799.00"},
                {"selector": ".a-unordered-list li:nth-child(1)", "text": "BUILT FOR APPLE INTELLIGENCE — Apple Intelligence is the personal intelligence system that helps you write, express yourself, and get things done effortlessly. With groundbreaking privacy protections, it gives you peace of mind that no one else can access your data."},
                {"selector": ".a-unordered-list li:nth-child(2)", "text": "SUPERCHARGED BY M3 PRO — The M3 Pro chip, with an 11-core CPU and 14-core GPU, enables MacBook Pro to fly through workflows in photography, videography, music production, and more."},
                {"selector": ".a-unordered-list li:nth-child(3)", "text": "UP TO 18 HOURS OF BATTERY LIFE — MacBook Pro delivers exceptional performance while also getting up to 18 hours of battery life, so you can keep going all day and into the night."},
                {"selector": ".a-unordered-list li:nth-child(4)", "text": "STUNNING LIQUID RETINA XDR DISPLAY — The 14.2-inch Liquid Retina XDR display with ProMotion technology featuring up to 120Hz adaptive refresh rate is 1,000 nits of sustained brightness for SDR content."},
                {"selector": "#acrCustomerReviewText", "text": "4.7 out of 5 stars · 2,341 ratings"},
                {"selector": ".a-section .a-unordered-list li", "text": "RAM: 18GB unified memory · Storage: 512GB SSD · Ports: 3x Thunderbolt 4, HDMI 2.1, SD card reader, MagSafe 3"},
                {"selector": "#feature-bullets li:nth-child(5)", "text": "ADVANCED CAMERA AND AUDIO — The 12MP Center Stage camera with Center Stage, Studio-quality three-mic array and six-speaker sound system with Spatial Audio support."},
            ],
            visible_text=(
                "Apple MacBook Pro 14-inch with M3 Pro chip\n"
                "Price: $1,799.00\n"
                "Rating: 4.7 out of 5 stars (2,341 ratings)\n\n"
                "Key features:\n"
                "• M3 Pro chip: 11-core CPU, 14-core GPU\n"
                "• 18GB unified memory, 512GB SSD\n"
                "• Up to 18 hours battery life\n"
                "• 14.2-inch Liquid Retina XDR display, 120Hz ProMotion\n"
                "• 1000 nits sustained brightness (1600 nits peak HDR)\n"
                "• 3x Thunderbolt 4, HDMI 2.1, SD card reader, MagSafe 3\n"
                "• 12MP Center Stage camera\n"
                "• Available in Space Black and Silver\n\n"
                "Built for Apple Intelligence — personal AI features with on-device privacy.\n\n"
                "In stock. Ships from and sold by Amazon.com. Free delivery on eligible orders.\n\n"
                "Frequently bought together with: Apple Magic Mouse, AppleCare+ for MacBook Pro\n\n"
                "Top customer review: 'The performance leap from my M1 Max is noticeable. "
                "Compiles are faster, battery is incredible, display is gorgeous. '"
            ),
            metadata={
                "description": "Buy Apple MacBook Pro 14-inch M3 Pro at Amazon. Best price, fast shipping.",
                "og:price:amount": "1799.00",
                "og:price:currency": "USD",
            },
        ),
        context_fingerprint="amz_mbp14_001",
        selection_scope="page",
    ),

    "blog_article_react_performance": AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message="in short",
        read_view=ReadView(
            url="https://kentcdodds.com/blog/fix-the-slow-render-before-you-fix-the-re-render",
            title="Fix the slow render before you fix the re-render | Kent C. Dodds",
            headings=[
                "Fix the slow render before you fix the re-render",
                "The common mistake",
                "Measuring is everything",
                "The React DevTools Profiler",
                "Where does the time actually go?",
                "Common causes of slow renders",
                "What about memo?",
                "When to optimize",
                "Conclusion",
            ],
            content_blocks=[
                {"selector": "article p:nth-child(1)", "text": "One of the most common mistakes I see React developers make is to try to fix a performance problem by memoizing components or adding useMemo hooks everywhere before actually measuring what's happening."},
                {"selector": "article p:nth-child(2)", "text": "The thing is, if a component renders slowly, it doesn't matter how few re-renders it does. A component that renders once but takes 500ms to do so will still make your app feel terrible."},
                {"selector": "article p:nth-child(3)", "text": "Before you reach for React.memo, useCallback, or useMemo, open the React DevTools Profiler. Record a user interaction. Look at the flame graph. Find what's actually slow. Often you'll find that the problem has nothing to do with unnecessary re-renders."},
                {"selector": "article p:nth-child(4)", "text": "Common causes of slow renders: 1) Expensive computations in render (should be memoized with useMemo), 2) Large DOM trees being rendered (virtualize with react-window), 3) Missing key props causing full tree reconciliation, 4) Synchronous data fetching blocking the thread, 5) Heavy third-party libraries loaded on every render."},
                {"selector": "article p:nth-child(5)", "text": "React.memo and useMemo are not free. They add overhead: the props comparison on every parent render. If your component is already fast, memoization makes it slower. Only memoize when you've measured a benefit."},
                {"selector": "article p:nth-child(6)", "text": "The rule of thumb: 1) Measure first with the Profiler. 2) Fix the component's own render (the slow render). 3) Then, if re-renders are still a problem, reduce them with memo. Never skip step 1 and 2 to jump to step 3."},
                {"selector": "article .author-date", "text": "Kent C. Dodds · April 2023 · 8 min read"},
                {"selector": "article .conclusion", "text": "In conclusion: profile first, optimize the render body second, and only then reach for memoization. You'll solve more problems and ship fewer regressions."},
            ],
            visible_text=(
                "Fix the slow render before you fix the re-render\n"
                "Kent C. Dodds · April 2023 · 8 min read\n\n"
                "One of the most common mistakes React developers make is memoizing components everywhere "
                "before measuring what's actually slow. If a component renders once but takes 500ms, "
                "it will still make your app feel terrible no matter how few re-renders it does.\n\n"
                "Before reaching for React.memo, useCallback, or useMemo, open the React DevTools Profiler. "
                "Record a user interaction. Look at the flame graph. Find what's actually slow.\n\n"
                "Common causes of slow renders:\n"
                "1. Expensive computations in render (use useMemo)\n"
                "2. Large DOM trees (virtualize with react-window)\n"
                "3. Missing key props causing full reconciliation\n"
                "4. Synchronous data fetching blocking the thread\n"
                "5. Heavy third-party libraries loaded on every render\n\n"
                "React.memo is not free — it adds overhead on every parent render for the props comparison. "
                "If your component is already fast, memoization makes it slower.\n\n"
                "The rule: Profile first → fix the component render → then reduce re-renders with memo. "
                "Never skip to step 3. Profile first. Always.\n\n"
                "Conclusion: profile first, optimize the render body second, memoize only when measured."
            ),
            metadata={
                "description": "How to actually fix React performance problems: measure before optimizing",
                "author": "Kent C. Dodds",
                "og:type": "article",
            },
        ),
        context_fingerprint="kcd_react_perf_001",
        selection_scope="page",
    ),
}


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_validation():
    results = {}

    for name, request in PAGES.items():
        print(f"\n{'='*60}")
        print(f"TEST: {name}")
        print(f"URL:  {request.read_view.url}")
        print(f"MSG:  '{request.message}'")
        print(f"{'='*60}")

        t0 = time.monotonic()
        try:
            response = run(request)
            elapsed = time.monotonic() - t0

            results[name] = {
                "status": "ok",
                "intent": response.intent,
                "routed_to": response.routed_to,
                "type": response.type,
                "latency_s": round(elapsed, 2),
                "context_chars": response.meta.context_chars,
                "response_meta_latency_ms": response.meta.latency_ms,
                "content": response.content if isinstance(response.content, dict) else str(response.content),
                "suggested_followups": response.suggested_followups,
                "available_actions": response.available_actions,
                "handoff": {"available": response.handoff.available, "target": response.handoff.target},
            }

            if response.type == "summary":
                c = response.content
                content_dict = c.model_dump() if hasattr(c, "model_dump") else c
                print(f"  intent      : {response.intent} -> {response.routed_to}")
                print(f"  context_chars: {response.meta.context_chars}")
                print(f"  latency     : {elapsed:.2f}s (meta: {response.meta.latency_ms}ms)")
                print(f"  tldr        : {content_dict.get('tldr', '')[:120]}")
                print(f"  key_points  : {len(content_dict.get('key_points', []))} items")
                for kp in content_dict.get("key_points", [])[:3]:
                    print(f"    - {kp[:100]}")
                print(f"  entities    : {len(content_dict.get('entities', []))} items")
                for e in content_dict.get("entities", [])[:3]:
                    print(f"    - {e}")
                print(f"  actions     : {content_dict.get('available_actions', [])}")
            else:
                print(f"  type: {response.type}")
                print(f"  content: {str(response.content)[:200]}")

        except Exception as exc:
            elapsed = time.monotonic() - t0
            results[name] = {
                "status": "error",
                "error": str(exc),
                "latency_s": round(elapsed, 2),
            }
            print(f"  ERROR ({elapsed:.2f}s): {exc}")

    # Write full JSON results
    out_path = os.path.join(os.path.dirname(__file__), "validation_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n\nFull results written to: {out_path}")
    return results


if __name__ == "__main__":
    run_validation()
