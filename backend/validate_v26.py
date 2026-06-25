"""
V2.6 Cognitive Core — Live Validation Script

Sections:
  1. Compare two products → entity extraction
  2. Follow-up comparison → entity reference in subsequent turn
  3. Entity reference resolution (it / first / second)
  4. Goal tracking across turns
  5. Workflow handoff enrichment (entities + goal in payload)
  6. Latency benchmarks — must not regress summarize or ask paths
  7. Regression — Slices 1-4 behavior unchanged
"""
import io, json, os, sys, time, uuid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(__file__))

from app.schemas.assist import AssistRequest, ReadView
from app.assist.ambient_assistant import run
from app.conversation import manager as conversation_manager
from app.cognitive_core import conversation_manager as cog_mgr
from app.cognitive_core import analytics as cog_analytics

PASS = "OK"
FAIL = "FAIL"
results: list[dict] = []


def _rv(text: str = "MacBook Air costs $1099. Dell XPS costs $999.") -> ReadView:
    return ReadView(
        url="https://example.com/laptops",
        title="Laptop Comparison",
        headings=["Top Laptops"],
        content_blocks=[{"selector": "p", "text": text}],
        visible_text=text,
        metadata={},
    )


def _req(message: str, cid: str) -> AssistRequest:
    return AssistRequest(
        conversation_id=cid,
        message=message,
        read_view=_rv(),
        context_fingerprint="test",
        selection_scope="page",
    )


def _reset():
    conversation_manager._reset_store_for_testing()
    cog_mgr._reset_for_testing()
    cog_analytics._reset_for_testing()


def _record(section: str, label: str, ok: bool, detail: str = ""):
    status = PASS if ok else FAIL
    results.append({"section": section, "label": label, "status": status, "detail": detail})
    mark = "[OK]" if ok else "[FAIL]"
    print(f"  {mark}  {label}" + (f"  ({detail})" if detail else ""))
    return ok


def _mock_summary(entities: list | None = None) -> str:
    return json.dumps({
        "tldr": "Two laptops compared.",
        "key_points": ["MacBook Air: $1099", "Dell XPS: $999"],
        "entities": entities or [
            {"label": "Product", "value": "MacBook Air"},
            {"label": "Product", "value": "Dell XPS"},
        ],
        "available_actions": [],
    })


# ── SECTION 1: Compare two products — entity extraction ──────────────────────

def section1_compare_entity_extraction():
    print("\n" + "="*60)
    print("SECTION 1 — Compare two products → entity extraction")
    print("="*60)
    _reset()
    cid = str(uuid.uuid4())

    resp = run(_req("compare MacBook Air and Dell XPS", cid))
    session = cog_mgr.get_session(cid)

    print(f"\n  response.type={resp.type}  intent={resp.intent}")
    _record("1_entity_extraction", "response type=not_implemented", resp.type == "not_implemented")
    _record("1_entity_extraction", "session created", session is not None)

    if session:
        names = {e.name for e in session.active_entities.values()}
        print(f"  entities: {names}")
        _record("1_entity_extraction", "MacBook Air extracted", "MacBook Air" in names)
        _record("1_entity_extraction", "Dell XPS extracted", "Dell XPS" in names)
        _record("1_entity_extraction", "entity_order has 2+ entries", len(session.entity_order) >= 2)
    else:
        for label in ["MacBook Air extracted", "Dell XPS extracted", "entity_order has 2+ entries"]:
            _record("1_entity_extraction", label, False, "no session")


# ── SECTION 2: Follow-up after comparison ────────────────────────────────────

def section2_followup_comparison():
    print("\n" + "="*60)
    print("SECTION 2 — Follow-up after compare → entities survive")
    print("="*60)
    from unittest.mock import patch
    _reset()
    cid = str(uuid.uuid4())

    # Turn 1: compare
    run(_req("compare MacBook Air and Dell XPS", cid))

    # Turn 2: ask follow-up (with reference)
    with patch("app.services.ai_service.generate_text", return_value="Dell XPS at $999 is cheaper."):
        resp = run(_req("which is cheaper?", cid))

    session = cog_mgr.get_session(cid)
    print(f"\n  turn2.type={resp.type}  session.turn_count={session.turn_count if session else 'N/A'}")
    _record("2_followup", "follow-up responded with answer", resp.type == "answer")
    _record("2_followup", "session turn_count=2", session is not None and session.turn_count == 2)

    if session:
        names = {e.name for e in session.active_entities.values()}
        print(f"  entities after 2 turns: {names}")
        _record("2_followup", "MacBook Air still in session", "MacBook Air" in names)
        _record("2_followup", "Dell XPS still in session", "Dell XPS" in names)
    else:
        _record("2_followup", "MacBook Air still in session", False)
        _record("2_followup", "Dell XPS still in session", False)


# ── SECTION 3: Entity reference resolution ───────────────────────────────────

def section3_reference_resolution():
    print("\n" + "="*60)
    print("SECTION 3 — Reference resolution")
    print("="*60)
    from app.cognitive_core import reference_resolver
    from app.cognitive_core.models import CognitiveSession, Entity, EntityType
    from app.cognitive_core.entity_registry import _upsert_entity

    def _session_with(*names) -> CognitiveSession:
        s = CognitiveSession(conversation_id=str(uuid.uuid4()))
        for i, n in enumerate(names):
            _upsert_entity(s, Entity(id=str(uuid.uuid4()), type=EntityType.product, name=n, source_turn=i))
        return s

    # Ordinal
    s = _session_with("MacBook Air", "Dell XPS")
    r = reference_resolver.resolve("Show me the first one", s)
    print(f"\n  'first one' → {r.entity_name} (method={r.method}, conf={r.confidence:.2f})")
    _record("3_resolution", "ordinal 'first' → MacBook Air", r.entity_name == "MacBook Air" and r.method == "ordinal")

    r = reference_resolver.resolve("Tell me about the second", s)
    print(f"  'second' → {r.entity_name} (method={r.method}, conf={r.confidence:.2f})")
    _record("3_resolution", "ordinal 'second' → Dell XPS", r.entity_name == "Dell XPS" and r.method == "ordinal")

    # Proximal
    r = reference_resolver.resolve("Research it", s)
    print(f"  'it' → {r.entity_name} (method={r.method}, conf={r.confidence:.2f})")
    _record("3_resolution", "proximal 'it' → most recent (Dell XPS)", r.entity_name == "Dell XPS" and r.method == "proximal")

    # Name match
    r = reference_resolver.resolve("Tell me more about MacBook Air", s)
    print(f"  name-match 'MacBook Air' → {r.entity_name} (method={r.method})")
    _record("3_resolution", "name match → MacBook Air", r.entity_name == "MacBook Air" and r.method == "name_match")

    # No match
    empty = CognitiveSession(conversation_id=str(uuid.uuid4()))
    r = reference_resolver.resolve("What is this?", empty)
    _record("3_resolution", "empty session → method=none", r.method == "none" and r.entity_id is None)


# ── SECTION 4: Goal tracking ─────────────────────────────────────────────────

def section4_goal_tracking():
    print("\n" + "="*60)
    print("SECTION 4 — Goal tracking across turns")
    print("="*60)
    from unittest.mock import patch
    _reset()
    cid = str(uuid.uuid4())

    # Turn 1: compare (creates goal)
    run(_req("compare MacBook Air and Dell XPS", cid))
    session = cog_mgr.get_session(cid)
    goal1 = session.active_goal if session else None
    print(f"\n  Turn 1 goal: '{goal1.goal_text if goal1 else None}'  status={goal1.status if goal1 else None}")
    _record("4_goal", "goal created on first turn", goal1 is not None)
    _record("4_goal", "compare goal text has entity names or 'Compare'",
            goal1 is not None and ("Compare" in goal1.goal_text or "MacBook" in goal1.goal_text))
    _record("4_goal", "goal status=handed_off (compare→handoff)", goal1 is not None and goal1.status.value == "handed_off")

    goal1_id = goal1.goal_id if goal1 else None

    # Turn 2: ask follow-up
    with patch("app.services.ai_service.generate_text", return_value="Dell XPS is cheaper."):
        run(_req("which is cheaper?", cid))
    goal2 = session.active_goal if session else None
    print(f"  Turn 2 goal: '{goal2.goal_text if goal2 else None}'  status={goal2.status if goal2 else None}")
    _record("4_goal", "goal id unchanged across turns", goal2 is not None and goal2.goal_id == goal1_id)

    # Turn 3: handoff (research)
    run(_req("research that laptop", cid))
    goal3 = session.active_goal if session else None
    print(f"  Turn 3 goal: '{goal3.goal_text if goal3 else None}'  status={goal3.status if goal3 else None}")
    _record("4_goal", "research triggers handed_off status", goal3 is not None and goal3.status.value == "handed_off")


# ── SECTION 5: Workflow handoff enrichment ───────────────────────────────────

def section5_handoff_enrichment():
    print("\n" + "="*60)
    print("SECTION 5 — Workflow handoff enrichment")
    print("="*60)
    _reset()
    cid = str(uuid.uuid4())

    # Turn 1: compare (loads entities)
    run(_req("compare MacBook Air and Dell XPS", cid))

    # Turn 2: research (triggers handoff with enriched payload)
    resp = run(_req("research that laptop", cid))

    print(f"\n  handoff.available={resp.handoff.available}  handoff.target={resp.handoff.target!r}")
    print(f"  handoff_payload is None: {resp.handoff_payload is None}")

    _record("5_handoff_enrichment", "handoff.available=True", resp.handoff.available is True)
    _record("5_handoff_enrichment", "handoff_payload not None", resp.handoff_payload is not None)

    if resp.handoff_payload:
        p = resp.handoff_payload
        print(f"  query='{p.query}'")
        print(f"  entities: {[e.name for e in p.entities]}")
        print(f"  goal_text='{p.goal_text}'  goal_status='{p.goal_status}'")
        print(f"  turn_count={p.turn_count}  summary='{p.conversation_summary[:50]}'")
        _record("5_handoff_enrichment", "payload.query preserved", p.query == "research that laptop")
        _record("5_handoff_enrichment", "payload has entities from turn 1", len(p.entities) >= 2)
        _record("5_handoff_enrichment", "payload.goal_text not None", p.goal_text is not None)
        _record("5_handoff_enrichment", "payload.goal_status not None", p.goal_status is not None)
        _record("5_handoff_enrichment", "payload.turn_count=2", p.turn_count == 2)
        _record("5_handoff_enrichment", "payload serializable", bool(p.model_dump()))
    else:
        for label in ["payload.query preserved", "payload has entities from turn 1",
                      "payload.goal_text not None", "payload.goal_status not None",
                      "payload.turn_count=2", "payload serializable"]:
            _record("5_handoff_enrichment", label, False, "no handoff_payload")


# ── SECTION 6: Latency benchmarks ────────────────────────────────────────────

def section6_latency_benchmarks():
    print("\n" + "="*60)
    print("SECTION 6 — Latency benchmarks")
    print("="*60)
    from unittest.mock import patch
    _reset()

    # Fallback (cognitive overhead only — no LLM)
    fallback_times: list[int] = []
    for i in range(5):
        _reset()
        cid = str(uuid.uuid4())
        t0 = time.monotonic()
        run(_req("compare MacBook Air and Dell XPS", cid))
        elapsed = int((time.monotonic() - t0) * 1000)
        fallback_times.append(elapsed)
    avg_fallback = sum(fallback_times) / len(fallback_times)
    print(f"\n  Fallback (compare): {fallback_times}ms  avg={avg_fallback:.1f}ms")
    _record("6_latency", "fallback avg < 10ms (no LLM)", avg_fallback < 10, f"{avg_fallback:.1f}ms")

    # Cognitive overhead on ask path (measure ONLY overhead, mock LLM)
    ask_times_with_entities: list[int] = []
    for i in range(5):
        _reset()
        cid = str(uuid.uuid4())
        # Pre-load entities into session
        from app.cognitive_core.models import CognitiveSession, Entity, EntityType
        from app.cognitive_core.entity_registry import _upsert_entity
        session = cog_mgr.get_or_create(cid)
        _upsert_entity(session, Entity(id=str(uuid.uuid4()), type=EntityType.product, name="MacBook Air"))
        _upsert_entity(session, Entity(id=str(uuid.uuid4()), type=EntityType.product, name="Dell XPS"))

        # Mock LLM to isolate cognitive overhead
        with patch("app.services.ai_service.generate_text", return_value="Dell XPS is cheaper."):
            t0 = time.monotonic()
            run(_req("which is cheaper?", cid))
            elapsed = int((time.monotonic() - t0) * 1000)
        ask_times_with_entities.append(elapsed)

    avg_ask = sum(ask_times_with_entities) / len(ask_times_with_entities)
    print(f"  Ask with enrichment (mocked LLM): {ask_times_with_entities}ms  avg={avg_ask:.1f}ms")
    _record("6_latency", "ask cognitive overhead < 5ms", avg_ask < 5, f"{avg_ask:.1f}ms")

    # Research handoff overhead
    research_times: list[int] = []
    for i in range(5):
        _reset()
        cid = str(uuid.uuid4())
        t0 = time.monotonic()
        run(_req("research quantum computing", cid))
        elapsed = int((time.monotonic() - t0) * 1000)
        research_times.append(elapsed)
    avg_research = sum(research_times) / len(research_times)
    print(f"  Research handoff: {research_times}ms  avg={avg_research:.1f}ms")
    _record("6_latency", "research+payload build < 10ms", avg_research < 10, f"{avg_research:.1f}ms")


# ── SECTION 7: Regression ─────────────────────────────────────────────────────

def section7_regression():
    print("\n" + "="*60)
    print("SECTION 7 — Regression (Slices 1-4 behavior unchanged)")
    print("="*60)
    from unittest.mock import patch
    _reset()

    # Summarize → unchanged
    cid = str(uuid.uuid4())
    with patch("app.services.ai_service.generate_text", return_value=_mock_summary()):
        with patch("app.services.followup_service.generate", return_value=["Tell me more"]):
            resp = run(_req("summarize this page", cid))
    print(f"\n  summarize: type={resp.type}  handoff.available={resp.handoff.available}  payload={resp.handoff_payload is None}")
    _record("7_regression", "summarize type=summary", resp.type == "summary")
    _record("7_regression", "summarize handoff.available=False", resp.handoff.available is False)
    _record("7_regression", "summarize handoff_payload=None", resp.handoff_payload is None)
    _record("7_regression", "summarize followups preserved", len(resp.suggested_followups) > 0)

    # Ask → Option B preserved
    _reset()
    cid = str(uuid.uuid4())
    with patch("app.services.ai_service.generate_text", return_value="FastAPI answer."):
        resp = run(_req("what is FastAPI?", cid))
    print(f"  ask: type={resp.type}  followups={resp.suggested_followups}  payload={resp.handoff_payload is None}")
    _record("7_regression", "ask type=answer", resp.type == "answer")
    _record("7_regression", "ask suggested_followups=[] (Option B)", resp.suggested_followups == [])
    _record("7_regression", "ask handoff.available=False", resp.handoff.available is False)
    _record("7_regression", "ask handoff_payload=None", resp.handoff_payload is None)

    # Research → handoff preserved + now enriched
    _reset()
    cid = str(uuid.uuid4())
    resp = run(_req("research artificial intelligence", cid))
    print(f"  research: type={resp.type}  handoff.available={resp.handoff.available}  target={resp.handoff.target!r}")
    _record("7_regression", "research handoff.available=True", resp.handoff.available is True)
    _record("7_regression", "research handoff.target=workflow", resp.handoff.target == "workflow")
    _record("7_regression", "research handoff_payload not None (V2.6)", resp.handoff_payload is not None)


# ── Run all ───────────────────────────────────────────────────────────────────

def run_validation():
    print("\nV2.6 Cognitive Core — Live Validation")

    section1_compare_entity_extraction()
    section2_followup_comparison()
    section3_reference_resolution()
    section4_goal_tracking()
    section5_handoff_enrichment()
    section6_latency_benchmarks()
    section7_regression()

    total = len(results)
    passed = sum(1 for r in results if r["status"] == PASS)
    failed = total - passed

    print(f"\n{'='*60}")
    print(f"VALIDATION COMPLETE — V2.6 Cognitive Core")
    print(f"  Total:  {total}")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")

    if failed:
        print("\nFAILED:")
        for r in results:
            if r["status"] == FAIL:
                print(f"  [{r['section']}] {r['label']}  {r['detail']}")

    out = os.path.join(os.path.dirname(__file__), "validation_results_v26.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"  Results: {out}")

    return failed == 0


if __name__ == "__main__":
    success = run_validation()
    sys.exit(0 if success else 1)
