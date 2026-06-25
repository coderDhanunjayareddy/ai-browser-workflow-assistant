"""Unit tests for cognitive_core.goal_tracker."""
import uuid

from app.cognitive_core.models import CognitiveSession, Entity, EntityType, GoalStatus
from app.cognitive_core import goal_tracker


def _entity(name: str) -> Entity:
    return Entity(id=str(uuid.uuid4()), type=EntityType.product, name=name)


def _session() -> CognitiveSession:
    return CognitiveSession(conversation_id=str(uuid.uuid4()))


# ── infer_goal ────────────────────────────────────────────────────────────────

class TestInferGoal:
    def test_summarize_intent(self):
        goal = goal_tracker.infer_goal("summarize", "summarize this page", [])
        assert goal.goal_text == "Understand this page"
        assert goal.status == GoalStatus.active

    def test_ask_intent_includes_question(self):
        goal = goal_tracker.infer_goal("ask", "What is the price of shipping?", [])
        assert "Find:" in goal.goal_text
        assert "What is the price" in goal.goal_text

    def test_compare_intent_with_entities(self):
        entities = [_entity("MacBook Air"), _entity("Dell XPS")]
        goal = goal_tracker.infer_goal("compare", "compare these", entities)
        assert "Compare:" in goal.goal_text
        assert "MacBook Air" in goal.goal_text
        assert "Dell XPS" in goal.goal_text

    def test_compare_intent_no_entities(self):
        goal = goal_tracker.infer_goal("compare", "compare the two laptops", [])
        assert "Compare:" in goal.goal_text

    def test_research_intent(self):
        goal = goal_tracker.infer_goal("research", "research quantum computing", [])
        assert "Research:" in goal.goal_text

    def test_unknown_intent(self):
        goal = goal_tracker.infer_goal("unknown", "book me a flight", [])
        assert "Complete:" in goal.goal_text

    def test_goal_starts_active(self):
        goal = goal_tracker.infer_goal("summarize", "summarize", [])
        assert goal.status == GoalStatus.active

    def test_goal_id_unique(self):
        g1 = goal_tracker.infer_goal("ask", "question 1", [])
        g2 = goal_tracker.infer_goal("ask", "question 2", [])
        assert g1.goal_id != g2.goal_id

    def test_ask_question_truncated_at_60(self):
        long_q = "a" * 100
        goal = goal_tracker.infer_goal("ask", long_q, [])
        assert len(goal.goal_text) < 80  # "Find: " + 60 chars max


# ── update_goal ───────────────────────────────────────────────────────────────

class TestUpdateGoal:
    def test_handoff_sets_handed_off(self):
        goal = goal_tracker.infer_goal("research", "research AI", [])
        updated = goal_tracker.update_goal(goal, "research", "not_implemented", handoff_triggered=True)
        assert updated.status == GoalStatus.handed_off

    def test_summarize_success_marks_completed(self):
        goal = goal_tracker.infer_goal("summarize", "summarize", [])
        updated = goal_tracker.update_goal(goal, "summarize", "summary")
        assert updated.status == GoalStatus.completed

    def test_ask_success_stays_active(self):
        goal = goal_tracker.infer_goal("ask", "what is this?", [])
        updated = goal_tracker.update_goal(goal, "ask", "answer")
        assert updated.status == GoalStatus.active

    def test_errors_trigger_blocked(self):
        goal = goal_tracker.infer_goal("ask", "question", [])
        updated = goal_tracker.update_goal(goal, "ask", "error", consecutive_errors=3)
        assert updated.status == GoalStatus.blocked


# ── evolve_goal ───────────────────────────────────────────────────────────────

class TestEvolveGoal:
    def test_creates_goal_on_first_turn(self):
        s = _session()
        assert s.active_goal is None
        goal_tracker.evolve_goal(s, "summarize", "summarize page", [], "summary")
        assert s.active_goal is not None
        assert s.active_goal.goal_text == "Understand this page"

    def test_updates_goal_on_subsequent_turns(self):
        s = _session()
        goal_tracker.evolve_goal(s, "summarize", "summarize", [], "summary")
        first_id = s.active_goal.goal_id  # type: ignore[union-attr]
        goal_tracker.evolve_goal(s, "ask", "question", [], "answer")
        assert s.active_goal.goal_id == first_id  # same goal, not replaced

    def test_compare_goal_text_refined_with_entities(self):
        s = _session()
        entities = [_entity("MacBook Air"), _entity("Dell XPS")]
        goal_tracker.evolve_goal(s, "compare", "compare them", entities, "not_implemented")
        assert "MacBook Air" in s.active_goal.goal_text  # type: ignore[union-attr]

    def test_handoff_transitions_goal_to_handed_off(self):
        s = _session()
        goal_tracker.evolve_goal(s, "research", "research AI", [], "not_implemented", handoff_triggered=True)
        assert s.active_goal.status == GoalStatus.handed_off  # type: ignore[union-attr]
