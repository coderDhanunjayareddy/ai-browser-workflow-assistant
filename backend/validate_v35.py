"""
V3.5 Research Session Engine -- Live Validation Script.

Validates all V3.5 components without requiring a running server.
Run from backend/ directory:
  PYTHONIOENCODING=utf-8 python validate_v35.py

Exit code: 0 = all checks pass, 1 = one or more failures.
"""
import sys
import json
import uuid
from unittest.mock import patch, MagicMock

PASS = "[PASS]"
FAIL = "[FAIL]"
SEP  = "-" * 60

results: list[bool] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    symbol = PASS if ok else FAIL
    print(f"  {symbol} {name}" + (f" -- {detail}" if detail else ""))
    results.append(ok)


def section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"  {title}")
    print(SEP)


# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Models
# ─────────────────────────────────────────────────────────────────────────────
section("1. Research Models")

try:
    from app.research.models import (
        ResearchStatus, SourceType, ResearchSource,
        ResearchPlan, ResearchReport, ResearchSession,
    )
    check("ResearchStatus enum values", set(v.value for v in ResearchStatus) == {"active","completed","failed","abandoned"})
    check("SourceType enum values", set(v.value for v in SourceType) == {"web","page_context","ai_knowledge"})
    src = ResearchSource(source_id=str(uuid.uuid4()), title="T", url="u", source_type=SourceType.web, snippet="s")
    check("ResearchSource instantiation", src.credibility_score == 0.7)
    plan = ResearchPlan(topic="AI", queries=["AI"])
    check("ResearchPlan has 4 stages", len(plan.stages) == 4)
    report = ResearchReport(executive_summary="s", key_findings=[], supporting_evidence=[], risks=[], open_questions=[], recommended_actions=[])
    check("ResearchReport default confidence=0.7", report.confidence_score == 0.7)
    sess = ResearchSession(session_id=str(uuid.uuid4()), conversation_id="c1", topic="AI")
    check("ResearchSession default status active", sess.status == ResearchStatus.active)
    check("ResearchSession synthesis_count=0", sess.synthesis_count == 0)
except Exception as e:
    check("Models import/instantiate", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Section 2: Planner
# ─────────────────────────────────────────────────────────────────────────────
section("2. Research Planner")

try:
    from app.research.planner import extract_topic, create_plan

    check("extract_topic strips 'research '", extract_topic("research quantum computing") == "quantum computing")
    check("extract_topic strips 'look up '", extract_topic("look up flight prices") == "flight prices")
    check("extract_topic no prefix unchanged", extract_topic("climate change") == "climate change")

    plan = create_plan("research machine learning")
    check("plan topic extracted", plan.topic == "machine learning")
    check("plan has queries", len(plan.queries) >= 1)
    check("first query is topic", plan.queries[0] == "machine learning")
    check("plan has overview query", any("overview" in q for q in plan.queries))
    check("plan has 4 stages", len(plan.stages) == 4)
    check("no duplicate queries", len(plan.queries) == len(set(plan.queries)))
except Exception as e:
    check("Planner", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Section 3: PageContextProvider
# ─────────────────────────────────────────────────────────────────────────────
section("3. PageContextProvider")

try:
    from app.research.providers.page_context import PageContextProvider
    from app.schemas.assist import ReadView
    import pytest as _pytest

    p = PageContextProvider()
    rv = ReadView(url="https://example.com", title="Test Page", visible_text="Important content here.")
    sources = p.search_page("query", rv)
    check("returns one source", len(sources) == 1)
    check("source_type = page_context", sources[0].source_type.value == "page_context")
    check("credibility = 0.9", sources[0].credibility_score == 0.9)
    check("title from read_view", sources[0].title == "Test Page")
    check("url from read_view", sources[0].url == "https://example.com")
    check("snippet contains visible text", "Important content" in sources[0].snippet)

    rv_empty = ReadView(url="https://example.com", title="T", visible_text="")
    check("empty visible_text returns empty", p.search_page("q", rv_empty) == [])

    try:
        p.search("query")
        check("search() raises NotImplementedError", False)
    except NotImplementedError:
        check("search() raises NotImplementedError", True)

except Exception as e:
    check("PageContextProvider", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Section 4: DuckDuckGoProvider
# ─────────────────────────────────────────────────────────────────────────────
section("4. DuckDuckGoProvider")

try:
    from app.research.providers.duckduckgo import DuckDuckGoProvider
    from app.research.models import SourceType

    p = DuckDuckGoProvider()

    ddg_data = {
        "AbstractText": "Python is a high-level programming language.",
        "AbstractURL": "https://en.wikipedia.org/wiki/Python",
        "AbstractSource": "Wikipedia",
        "Heading": "Python (programming language)",
        "RelatedTopics": [
            {"Text": "Django - A Python web framework", "FirstURL": "https://ddg.gg/django"},
            {"Text": "Flask - Lightweight Python web framework", "FirstURL": "https://ddg.gg/flask"},
        ],
    }
    sources = p._parse(ddg_data, max_results=5)
    check("parses abstract as web source", len(sources) >= 1)
    check("abstract credibility=0.8", sources[0].credibility_score == 0.8)
    check("abstract source_type=web", sources[0].source_type == SourceType.web)
    check("heading used as title", sources[0].title == "Python (programming language)")
    check("related topics parsed", len(sources) == 3)
    check("related topic credibility=0.7", sources[1].credibility_score == 0.7)

    empty_data = {"AbstractText": "", "AbstractURL": "", "AbstractSource": "", "Heading": "", "RelatedTopics": []}
    check("empty response returns empty list", p._parse(empty_data, 5) == [])

    with patch("httpx.Client") as mock_client:
        mock_client.return_value.__enter__.return_value.get.side_effect = Exception("timeout")
        result = p.search("query")
    check("HTTP error returns empty list gracefully", result == [])

except Exception as e:
    check("DuckDuckGoProvider", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Section 5: AIKnowledgeProvider
# ─────────────────────────────────────────────────────────────────────────────
section("5. AIKnowledgeProvider")

try:
    from app.research.providers.ai_knowledge import AIKnowledgeProvider
    from app.research.models import SourceType

    p = AIKnowledgeProvider()
    items = [
        {"title": "Python Basics", "snippet": "Python is a versatile language used in many domains."},
        {"title": "Python Use Cases", "snippet": "Used in web, data science, AI, and automation."},
    ]
    with patch("app.services.ai_service.generate_text", return_value=json.dumps(items)):
        sources = p.search("Python")
    check("returns 2 sources", len(sources) == 2)
    check("source_type = ai_knowledge", sources[0].source_type == SourceType.ai_knowledge)
    check("credibility = 0.5", sources[0].credibility_score == 0.5)
    check("url is empty string", sources[0].url == "")

    with patch("app.services.ai_service.generate_text", side_effect=Exception("API error")):
        result = p.search("test")
    check("LLM error returns empty list gracefully", result == [])

    fenced = f"```json\n{json.dumps(items)}\n```"
    with patch("app.services.ai_service.generate_text", return_value=fenced):
        result2 = p.search("Python")
    check("markdown fences stripped from response", len(result2) == 2)

except Exception as e:
    check("AIKnowledgeProvider", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Section 6: ResearchSynthesizer
# ─────────────────────────────────────────────────────────────────────────────
section("6. ResearchSynthesizer")

try:
    from app.research.synthesizer import synthesize, _compute_confidence, _stub_report
    from app.research.models import ResearchSource, SourceType

    src = ResearchSource(source_id=str(uuid.uuid4()), title="W", url="u", source_type=SourceType.web, snippet="s", credibility_score=0.8)

    mock_json = json.dumps({
        "executive_summary": "Python is a versatile language.",
        "key_findings": ["F1", "F2"],
        "supporting_evidence": [{"finding": "F1", "source_title": "W", "source_url": "u", "is_conclusion": False}],
        "risks": ["R1"],
        "open_questions": ["Q1?"],
        "recommended_actions": ["A1"],
        "confidence_score": 0.8,
    })
    with patch("app.services.ai_service.generate_text", return_value=mock_json):
        report = synthesize("Python", [src])
    check("executive_summary populated", report.executive_summary == "Python is a versatile language.")
    check("key_findings populated", "F1" in report.key_findings)
    check("confidence_score set", report.confidence_score == 0.8)
    check("risks populated", "R1" in report.risks)
    check("recommended_actions populated", "A1" in report.recommended_actions)

    with patch("app.services.ai_service.generate_text", side_effect=Exception("fail")):
        stub = synthesize("topic", [src])
    check("LLM error returns stub report", "topic" in stub.executive_summary)

    empty = synthesize("empty topic", [])
    check("empty sources returns stub with low confidence", empty.confidence_score == 0.3)

    check("confidence avg of [0.8, 0.6] = 0.7", _compute_confidence([src, ResearchSource(source_id="x", title="T", url="u", source_type=SourceType.web, snippet="s", credibility_score=0.6)]) == 0.7)

except Exception as e:
    check("Synthesizer", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Section 7: ResearchSessionManager
# ─────────────────────────────────────────────────────────────────────────────
section("7. ResearchSessionManager")

try:
    from app.research import session_manager
    from app.research.models import ResearchStatus

    session_manager._reset_for_testing()

    s = session_manager.create_session("c1", "AI")
    check("create_session returns session", s.conversation_id == "c1" and s.topic == "AI")
    check("initial status active", s.status == ResearchStatus.active)
    check("get_active returns session", session_manager.get_active("c1") is s)
    check("get_session by id", session_manager.get_session(s.session_id) is s)
    check("unknown conversation returns None", session_manager.get_active("unknown") is None)

    from app.research.models import ResearchPlan, ResearchReport, ResearchSource, SourceType
    plan = ResearchPlan(topic="AI", queries=["AI"])
    session_manager.attach_plan(s, plan)
    check("plan attached", s.plan is plan)

    src = ResearchSource(source_id=str(uuid.uuid4()), title="T", url="https://x.com", source_type=SourceType.web, snippet="s")
    session_manager.add_sources(s, [src])
    check("source added", len(s.sources) == 1)
    session_manager.add_sources(s, [src])  # duplicate
    check("duplicate URL not added", len(s.sources) == 1)

    rep = ResearchReport(executive_summary="S", key_findings=[], supporting_evidence=[], risks=[], open_questions=[], recommended_actions=[])
    session_manager.attach_report(s, rep)
    check("report attached", s.report is rep)
    check("status completed after report", s.status == ResearchStatus.completed)
    check("synthesis_count incremented", s.synthesis_count == 1)

    s2 = session_manager.create_session("c2", "B")
    session_manager.mark_failed(s2)
    check("mark_failed sets failed status", s2.status == ResearchStatus.failed)

    check("count_sessions = 2", session_manager.count_sessions() == 2)

except Exception as e:
    check("SessionManager", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Section 8: Intent Router + Research Route + Analytics
# ─────────────────────────────────────────────────────────────────────────────
section("8. Intent Router + Research Route + Analytics")

try:
    from app.intent.router import classify

    r = classify("research quantum computing")
    check("research routes to 'research'", r.route == "research")
    check("research intent is 'research'", r.intent == "research")

    r2 = classify("look up flight prices")
    check("look up routes to 'research'", r2.route == "research")

    r3 = classify("search for Python tutorials")
    check("search for routes to 'research'", r3.route == "research")

    r4 = classify("learn about machine learning")
    check("learn about routes to 'research'", r4.route == "research")

    r5 = classify("summarize this page")
    check("summarize still routes to 'light'", r5.route == "light")

    r6 = classify("compare iPhone vs Samsung")
    check("compare still routes to 'fallback'", r6.route == "fallback")

    r7 = classify("what is Python?")
    check("what is... still routes to 'light' (ask)", r7.route == "light")

    from app.research import analytics as ra
    ra._reset_for_testing()
    ra.record_session_started()
    ra.record_session_completed()
    ra.record_sources(3, used_page_context=True, used_ddg=True, used_ai_knowledge=False)
    ra.record_synthesis()
    ra.record_workflow_escalation()
    analytics_data = ra.get_analytics()
    check("analytics sessions_started=1", analytics_data["sessions_started"] == 1)
    check("analytics sessions_completed=1", analytics_data["sessions_completed"] == 1)
    check("analytics sources_collected=3", analytics_data["sources_collected"] == 3)
    check("analytics syntheses_run=1", analytics_data["syntheses_run"] == 1)
    check("analytics workflow_escalations=1", analytics_data["workflow_escalations"] == 1)
    check("analytics provider_uses tracked", analytics_data["provider_uses"]["page_context"] == 1)

except Exception as e:
    check("Intent Router + Analytics", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
passed = sum(results)
total  = len(results)
failed = total - passed

print(f"\n{SEP}")
print(f"  V3.5 Validation: {passed}/{total} checks passed  ({failed} failed)")
print(SEP)

if failed:
    print("  RESULT: FAILED")
    sys.exit(1)
else:
    print("  RESULT: ALL PASSED")
    sys.exit(0)
