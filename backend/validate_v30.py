"""
V3.0 Cognitive Memory + Workflow Consumption — Live Validation Script

8 sections, 40 checks. Runs without a live server — uses in-process imports,
SQLite in-memory DB, and patched AI calls.

Sections:
  1. MemoryStore — save/load/upsert round-trips
  2. Conversation Manager — DB restore on cache miss
  3. WorkflowContext — cognitive_context and bootstrap_facts
  4. StatePersistence — bootstrap_from_handoff (cold start + no-overwrite)
  5. ContextCompressor — cognitive_context 6th key
  6. WorkflowOrchestrator — handoff_payload wiring
  7. Cognitive REST endpoints — state, cleanup, analytics
  8. Regression — all V2.x paths unaffected
"""
import sys
import json
import traceback
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

# ── DB setup ──────────────────────────────────────────────────────────────────

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.db import Base, CognitiveSessionRecord

_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
Base.metadata.create_all(_engine)
_Session = sessionmaker(bind=_engine)


def fresh_db():
    """Return a clean in-memory SQLite session for each section."""
    eng = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    S = sessionmaker(bind=eng)
    return S()


# ── Validation harness ────────────────────────────────────────────────────────

_results: list[tuple[str, bool, str]] = []


def check(label: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    _results.append((label, condition, detail))
    marker = "+" if condition else "X"
    print(f"  {marker} [{status}] {label}" + (f" - {detail}" if detail else ""))


def section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ── Helpers ───────────────────────────────────────────────────────────────────

from app.cognitive_core.models import CognitiveSession, Entity, EntityType, Goal, GoalStatus
from app.schemas.assist import (
    AssistRequest, AssistResponse, ReadView,
    WorkflowHandoffPayload, CognitiveEntitySchema,
)
from app.cognitive_core import memory_store, conversation_manager as cog_mgr
from app.cognitive_core import analytics as cog_analytics
from app.conversation import manager as conv_mgr
from app.cognitive_core.workflow_context import build_cognitive_context, build_bootstrap_facts
from app.cognitive_core.memory_cleanup import cleanup_old_sessions, count_sessions


def _entity(name: str, eid: str = None) -> Entity:
    return Entity(
        id=eid or f"ent-{name.lower().replace(' ', '-')}",
        type=EntityType.product,
        name=name,
        confidence=0.9,
        source_turn=1,
    )


def _session_with_entity(cid: str, name: str) -> CognitiveSession:
    s = CognitiveSession(conversation_id=cid)
    s.turn_count = 3
    e = _entity(name)
    s.active_entities[e.id] = e
    s.entity_order = [e.id]
    s.conversation_summary = f"Discussing: {name}. Turn 3"
    return s


def _payload(goal="Compare laptops", entities=None, turns=3) -> WorkflowHandoffPayload:
    return WorkflowHandoffPayload(
        query="compare laptops",
        goal_text=goal,
        goal_status="active",
        entities=entities or [
            CognitiveEntitySchema(id="e1", type="product", name="MacBook Air",
                                  confidence=0.9, source_turn=1),
            CognitiveEntitySchema(id="e2", type="product", name="Dell XPS",
                                  confidence=0.6, source_turn=2),
        ],
        conversation_summary="Discussing: MacBook Air, Dell XPS.",
        turn_count=turns,
    )


def _request(cid: str, message: str) -> AssistRequest:
    return AssistRequest(
        conversation_id=cid,
        message=message,
        read_view=ReadView(
            title="Tech Reviews", url="https://tech.test",
            text="MacBook Air M3 vs Dell XPS 15.", headings=[], metadata={},
        ),
        selection_scope="page",
    )


def _reset():
    conv_mgr._reset_store_for_testing()
    cog_mgr._reset_for_testing()
    cog_mgr._skip_persistence = False
    cog_analytics._reset_for_testing()


# =============================================================================
# Section 1: MemoryStore
# =============================================================================

section("1. MemoryStore — save/load/upsert")

db = fresh_db()

s1 = _session_with_entity("mem-01", "MacBook Air")
s1.active_goal = Goal(
    goal_id="g1", goal_text="Compare laptops", status=GoalStatus.active,
    created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 2),
)
memory_store.save(db, s1)
r1 = memory_store.load(db, "mem-01")

check("1.1 load returns non-None", r1 is not None)
check("1.2 turn_count preserved", r1 is not None and r1.turn_count == 3)
check("1.3 entity restored", r1 is not None and "ent-macbook-air" in r1.active_entities)
check("1.4 entity name correct", r1 is not None and r1.active_entities.get("ent-macbook-air", MagicMock()).name == "MacBook Air")
check("1.5 goal restored", r1 is not None and r1.active_goal is not None)
check("1.6 goal text preserved", r1 is not None and r1.active_goal is not None and r1.active_goal.goal_text == "Compare laptops")

# Upsert
s1.turn_count = 7
s1.conversation_summary = "Updated"
memory_store.save(db, s1)
r1b = memory_store.load_record(db, "mem-01")
check("1.7 upsert increments turn_count", r1b is not None and r1b.turn_count == 7)
check("1.8 only one row after upsert", db.query(CognitiveSessionRecord).count() == 1)

# Missing key
check("1.9 load missing returns None", memory_store.load(db, "no-such-id") is None)
check("1.10 load_record missing returns None", memory_store.load_record(db, "no-such-id") is None)


# =============================================================================
# Section 2: Conversation Manager — DB restore on cache miss
# =============================================================================

section("2. Conversation Manager — DB restore on cache miss")

_reset()
db2 = fresh_db()

import uuid
cid2 = f"cm-{uuid.uuid4().hex[:8]}"
s2 = _session_with_entity(cid2, "Dell XPS")
s2.turn_count = 5
memory_store.save(db2, s2)

# Simulate cold start: clear in-memory cache, re-enable persistence
cog_mgr._reset_for_testing()
cog_mgr._skip_persistence = False

restored = cog_mgr.get_or_create(cid2, db=db2)
check("2.1 session restored from DB", restored.turn_count == 5)
check("2.2 entity restored from DB", "ent-dell-xps" in restored.active_entities)
check("2.3 restored_count incremented", cog_mgr._manager.restored_count() == 1)

# Second call hits in-memory cache
restored2 = cog_mgr.get_or_create(cid2, db=db2)
check("2.4 second call hits cache (not DB again)", cog_mgr._manager.restored_count() == 1)

# No-DB path still creates a new session
_reset()
fresh_session = cog_mgr.get_or_create("no-db-cid", db=None)
check("2.5 db=None creates new session without error", fresh_session.turn_count == 0)


# =============================================================================
# Section 3: WorkflowContext
# =============================================================================

section("3. WorkflowContext — cognitive_context and bootstrap_facts")

payload = _payload()
ctx = build_cognitive_context(payload)

check("3.1 conversation_turns present", ctx.get("conversation_turns") == 3)
check("3.2 conversation_summary present", "conversation_summary" in ctx)
check("3.3 user_goal present", ctx.get("user_goal") == "Compare laptops")
check("3.4 goal_status present", ctx.get("goal_status") == "active")
check("3.5 tracked_entities list", isinstance(ctx.get("tracked_entities"), list))
check("3.6 tracked_entities count", len(ctx.get("tracked_entities", [])) == 2)
check("3.7 entity confidence rounded", all(
    e["confidence"] == round(e["confidence"], 2)
    for e in ctx.get("tracked_entities", [])
))

facts = build_bootstrap_facts(payload)
check("3.8 user_goal in facts", facts.get("user_goal") == "Compare laptops")
check("3.9 entity_0_name correct", facts.get("entity_0_name") == "MacBook Air")
check("3.10 entity_1_name correct", facts.get("entity_1_name") == "Dell XPS")
check("3.11 prior_conversation_turns in facts", facts.get("prior_conversation_turns") == 3)

empty_payload = WorkflowHandoffPayload(query="x", goal_text=None, goal_status=None,
                                       entities=[], conversation_summary="", turn_count=0)
check("3.12 empty payload = empty facts dict", build_bootstrap_facts(empty_payload) == {})


# =============================================================================
# Section 4: StatePersistence — bootstrap_from_handoff
# =============================================================================

section("4. StatePersistence — bootstrap_from_handoff")

from app.state_engine.persistence import StatePersistence

db4 = fresh_db()
sp4 = StatePersistence(db4)

# Cold start — no existing state
state_cold = sp4.bootstrap_from_handoff("sess-cold", _payload())
check("4.1 cold-start returns state", state_cold is not None)
check("4.2 user_goal bootstrapped", state_cold is not None and state_cold.facts.get("user_goal") == "Compare laptops")
check("4.3 entity_0_name bootstrapped", state_cold is not None and state_cold.facts.get("entity_0_name") == "MacBook Air")
check("4.4 conversation_context bootstrapped", state_cold is not None and "conversation_context" in state_cold.facts)

# No-overwrite: existing facts preserved
db4b = fresh_db()
sp4b = StatePersistence(db4b)
sp4b.create_state("sess-existing", {"already": "here"})
state_existing = sp4b.bootstrap_from_handoff("sess-existing", _payload())
check("4.5 no-overwrite: existing facts preserved", state_existing is not None and state_existing.facts.get("already") == "here")
check("4.6 no-overwrite: user_goal NOT injected", state_existing is not None and "user_goal" not in state_existing.facts)

# None payload → None return
check("4.7 None payload returns None", sp4.bootstrap_from_handoff("any", None) is None)

# Empty payload → None or existing
empty_state = sp4.bootstrap_from_handoff("sess-empty", empty_payload)
check("4.8 empty payload = no facts created", empty_state is None or not empty_state.facts)


# =============================================================================
# Section 5: ContextCompressor — cognitive_context 6th key
# =============================================================================

section("5. ContextCompressor — cognitive_context 6th key")

from app.context_compression.compressor import ContextCompressor

pc = MagicMock()
pc.interactive_elements = []
compressor = ContextCompressor()

result_no_cog = compressor.compress(
    task="Do something", page_context=pc, verified_facts={}, prior_steps=[],
)
check("5.1 no cognitive_context = key absent", "cognitive_context" not in result_no_cog)
check("5.2 standard 5 keys present", all(k in result_no_cog for k in [
    "verified_facts", "active_goal", "relevant_elements", "important_failures", "task_constraints"
]))

cog_ctx = {"user_goal": "Compare laptops", "conversation_turns": 3}
result_with_cog = compressor.compress(
    task="Compare laptops", page_context=pc, verified_facts={}, prior_steps=[],
    cognitive_context=cog_ctx,
)
check("5.3 cognitive_context key present", "cognitive_context" in result_with_cog)
check("5.4 cognitive_context value correct", result_with_cog["cognitive_context"] == cog_ctx)
check("5.5 standard keys still present with cognitive_context", all(k in result_with_cog for k in [
    "verified_facts", "active_goal", "relevant_elements"
]))

empty_cog = {}
result_empty_cog = compressor.compress(
    task="x", page_context=pc, verified_facts={}, prior_steps=[],
    cognitive_context=empty_cog,
)
check("5.6 empty dict cognitive_context = key omitted", "cognitive_context" not in result_empty_cog)


# =============================================================================
# Section 6: WorkflowOrchestrator — handoff_payload wiring
# =============================================================================

section("6. WorkflowOrchestrator — handoff_payload wiring")

db6 = fresh_db()

from app.schemas.request import AnalyzeRequest, PageContext
from app.orchestrator.workflow_orchestrator import WorkflowOrchestrator

page_ctx = PageContext(
    url="https://tech.test",
    title="Tech Reviews",
    interactive_elements=[],
    content_blocks=[],
    headings=[],
    selected_text="",
    visible_text="",
    images=[],
)

payload6 = _payload()

mock_ai_result = MagicMock()
mock_ai_result.model_dump_json.return_value = '{"action": "none"}'

try:
    with (
        patch("app.services.ai_service.analyze", return_value=mock_ai_result),
        patch("app.services.ai_service.estimate_tokens", return_value=100),
        patch("app.services.analytics_service.record_planner_call"),
    ):
        orchestrator = WorkflowOrchestrator("orch-sess-1", db6)
        orchestrator.orchestrate_analysis(
            task="Compare laptops",
            page_context=page_ctx,
            prior_steps=[],
            supplemental_context="",
            handoff_payload=payload6,
        )

    # Verify WorkflowState.facts were bootstrapped
    from app.state_engine.persistence import StatePersistence
    sp6 = StatePersistence(db6)
    state6 = sp6.get_state("orch-sess-1")
    check("6.1 orchestrate_analysis accepts handoff_payload", True)
    check("6.2 bootstrap_from_handoff populated facts", state6 is not None and "user_goal" in (state6.facts or {}))
    check("6.3 entity fact in workflow state", state6 is not None and "entity_0_name" in (state6.facts or {}))
except Exception as exc:
    check("6.1 orchestrate_analysis accepts handoff_payload", False, str(exc))
    check("6.2 bootstrap_from_handoff populated facts", False)
    check("6.3 entity fact in workflow state", False)

# Verify None handoff_payload doesn't crash
try:
    with (
        patch("app.services.ai_service.analyze", return_value=mock_ai_result),
        patch("app.services.ai_service.estimate_tokens", return_value=100),
        patch("app.services.analytics_service.record_planner_call"),
    ):
        orch2 = WorkflowOrchestrator("orch-sess-2", fresh_db())
        orch2.orchestrate_analysis(
            task="Some task", page_context=page_ctx,
            prior_steps=[], supplemental_context="", handoff_payload=None,
        )
    check("6.4 None handoff_payload works without error", True)
except Exception as exc:
    check("6.4 None handoff_payload works without error", False, str(exc))


# =============================================================================
# Section 7: Cognitive REST endpoints — basic import + invocability
# =============================================================================

section("7. Cognitive REST endpoints")

try:
    from app.api.routes.cognitive import router as cog_router
    check("7.1 cognitive router imports", True)
    routes = {r.path for r in cog_router.routes}
    check("7.2 GET /cognitive/state/{conversation_id} registered",
          "/cognitive/state/{conversation_id}" in routes)
    check("7.3 POST /cognitive/cleanup registered",
          "/cognitive/cleanup" in routes)
    check("7.4 GET /cognitive/analytics registered",
          "/cognitive/analytics" in routes)
except Exception as exc:
    check("7.1 cognitive router imports", False, str(exc))
    check("7.2 GET /cognitive/state/{conversation_id} registered", False)
    check("7.3 POST /cognitive/cleanup registered", False)
    check("7.4 GET /cognitive/analytics registered", False)

# Verify router registered in app
try:
    from app.main import app
    all_paths = {r.path for r in app.routes}
    check("7.5 app includes /cognitive/state/{conversation_id}",
          "/cognitive/state/{conversation_id}" in all_paths)
    check("7.6 app includes /cognitive/cleanup",
          "/cognitive/cleanup" in all_paths)
    check("7.7 app includes /cognitive/analytics",
          "/cognitive/analytics" in all_paths)
except Exception as exc:
    check("7.5 app includes /cognitive/state/{conversation_id}", False, str(exc))
    check("7.6 app includes /cognitive/cleanup", False)
    check("7.7 app includes /cognitive/analytics", False)

# Memory cleanup logic
db7 = fresh_db()
for i in range(3):
    s = CognitiveSession(conversation_id=f"old-{i}")
    memory_store.save(db7, s)
db7.query(CognitiveSessionRecord).update({"updated_at": datetime.utcnow() - timedelta(days=40)})
db7.commit()
fresh_s = CognitiveSession(conversation_id="fresh-1")
memory_store.save(db7, fresh_s)

cleanup_stats = cleanup_old_sessions(db7, retention_days=30)
counts_after = count_sessions(db7)
check("7.8 cleanup deleted 3 old sessions", cleanup_stats["deleted_sessions"] == 3)
check("7.9 1 fresh session remains", counts_after["total_sessions"] == 1)


# =============================================================================
# Section 8: Regression — V2.x paths unaffected
# =============================================================================

section("8. Regression — V2.x paths unaffected")

_reset()
db8 = fresh_db()

from app.assist.ambient_assistant import run

def _mock_summary_obj():
    from app.schemas.assist import StructuredSummary
    return StructuredSummary(
        tldr="Tech review summary",
        key_points=["MacBook Air has better battery"],
        entities=[{"name": "MacBook Air", "type": "product"}],
        available_actions=[],
    )

mock_answer = MagicMock()
mock_answer.text = "MacBook Air has excellent battery life."

cid8 = f"reg-{uuid.uuid4().hex[:8]}"

# Summarize path
try:
    with (
        patch("app.assist.ambient_assistant.summarization_service.summarize", return_value=_mock_summary_obj()),
        patch("app.assist.ambient_assistant.followup_service.generate", return_value=["Tell me more"]),
        patch("app.intent.router.classify") as mc,
    ):
        mc.return_value = MagicMock(route="light", intent="summarize")
        resp_sum = run(_request(cid8, "Summarize this page"), db=db8)

    check("8.1 summarize returns AssistResponse", isinstance(resp_sum, AssistResponse))
    check("8.2 summarize type=summary", resp_sum.type == "summary")
    check("8.3 summarize handoff_payload=None", resp_sum.handoff_payload is None)
    check("8.4 summarize routed_to=light", resp_sum.routed_to == "light")
except Exception as exc:
    check("8.1 summarize returns AssistResponse", False, str(exc))
    check("8.2 summarize type=summary", False)
    check("8.3 summarize handoff_payload=None", False)
    check("8.4 summarize routed_to=light", False)

# Ask path
cid8b = f"reg-{uuid.uuid4().hex[:8]}"
try:
    with (
        patch("app.assist.ambient_assistant.qa_service.answer", return_value=mock_answer),
        patch("app.intent.router.classify") as mc,
    ):
        mc.return_value = MagicMock(route="light", intent="ask")
        resp_ask = run(_request(cid8b, "What is the battery life?"), db=db8)

    check("8.5 ask returns AssistResponse", isinstance(resp_ask, AssistResponse))
    check("8.6 ask type=answer", resp_ask.type == "answer")
    check("8.7 ask handoff_payload=None", resp_ask.handoff_payload is None)
    check("8.8 ask routed_to=light", resp_ask.routed_to == "light")
except Exception as exc:
    check("8.5 ask returns AssistResponse", False, str(exc))
    check("8.6 ask type=answer", False)
    check("8.7 ask handoff_payload=None", False)
    check("8.8 ask routed_to=light", False)

# Fallback path — with handoff_payload
cid8c = f"reg-{uuid.uuid4().hex[:8]}"
try:
    with patch("app.intent.router.classify") as mc:
        mc.return_value = MagicMock(route="fallback", intent="research")
        resp_fb = run(_request(cid8c, "Research MacBook Air battery life"), db=db8)

    check("8.9 fallback returns AssistResponse", isinstance(resp_fb, AssistResponse))
    check("8.10 fallback has handoff_payload", resp_fb.handoff_payload is not None)
    check("8.11 fallback query in handoff_payload", resp_fb.handoff_payload is not None and "MacBook" in resp_fb.handoff_payload.query)
    check("8.12 fallback handoff available=True", resp_fb.handoff.available is True)
except Exception as exc:
    check("8.9 fallback returns AssistResponse", False, str(exc))
    check("8.10 fallback has handoff_payload", False)
    check("8.11 fallback query in handoff_payload", False)
    check("8.12 fallback handoff available=True", False)


# =============================================================================
# Summary
# =============================================================================

total = len(_results)
passed = sum(1 for _, ok, _ in _results if ok)
failed = total - passed

print(f"\n{'='*60}")
print(f"  V3.0 VALIDATION RESULTS")
print(f"{'='*60}")
print(f"  Passed: {passed}/{total}")
print(f"  Failed: {failed}/{total}")

if failed > 0:
    print("\n  FAILING CHECKS:")
    for label, ok, detail in _results:
        if not ok:
            print(f"    X {label}" + (f" - {detail}" if detail else ""))

if failed == 0:
    print("\n  ALL CHECKS PASSED — V3.0 READY")
    sys.exit(0)
else:
    print("\n  VALIDATION FAILED — see failures above")
    sys.exit(1)
