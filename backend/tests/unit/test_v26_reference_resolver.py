"""Unit tests for cognitive_core.reference_resolver."""
import uuid

from app.cognitive_core.models import CognitiveSession, Entity, EntityType
from app.cognitive_core import reference_resolver
from app.cognitive_core import entity_registry


def _session_with_entities(*names: str) -> CognitiveSession:
    s = CognitiveSession(conversation_id=str(uuid.uuid4()))
    for i, name in enumerate(names):
        entity_registry._upsert_entity(
            s,
            Entity(id=str(uuid.uuid4()), type=EntityType.product, name=name, source_turn=i),
        )
    return s


# ── Ordinal resolution ────────────────────────────────────────────────────────

class TestOrdinalResolution:
    def test_first_resolves_to_index_zero(self):
        s = _session_with_entities("MacBook Air", "Dell XPS")
        result = reference_resolver.resolve("Show me the first one", s)
        assert result.method == "ordinal"
        assert result.entity_name == "MacBook Air"
        assert result.confidence >= 0.9

    def test_second_resolves_to_index_one(self):
        s = _session_with_entities("MacBook Air", "Dell XPS")
        result = reference_resolver.resolve("Tell me about the second", s)
        assert result.method == "ordinal"
        assert result.entity_name == "Dell XPS"

    def test_third_resolves_to_index_two(self):
        s = _session_with_entities("A", "B", "C")
        result = reference_resolver.resolve("Open the third one", s)
        assert result.method == "ordinal"
        assert result.entity_name == "C"

    def test_ordinal_out_of_range_falls_to_proximal(self):
        s = _session_with_entities("OnlyOne")
        result = reference_resolver.resolve("Show the second", s)
        # Only one entity — should fall back to proximal or none
        assert result.method in ("proximal", "none")

    def test_last_resolves_to_most_recent(self):
        s = _session_with_entities("A", "B", "C")
        result = reference_resolver.resolve("Open the last one", s)
        assert result.method == "ordinal"
        assert result.entity_name == "C"


# ── Proximal resolution ───────────────────────────────────────────────────────

class TestProximalResolution:
    def test_it_resolves_to_most_recent(self):
        s = _session_with_entities("MacBook Air", "Dell XPS")
        result = reference_resolver.resolve("Research it", s)
        assert result.method == "proximal"
        assert result.entity_name == "Dell XPS"

    def test_that_resolves_to_most_recent(self):
        s = _session_with_entities("iPhone")
        result = reference_resolver.resolve("Buy that", s)
        assert result.method == "proximal"
        assert result.entity_name == "iPhone"

    def test_this_one_resolves(self):
        s = _session_with_entities("Pixel 8")
        result = reference_resolver.resolve("Tell me more about this one", s)
        assert result.method == "proximal"
        assert result.entity_name == "Pixel 8"

    def test_those_resolves_to_most_recent(self):
        s = _session_with_entities("A", "B")
        result = reference_resolver.resolve("Compare those", s)
        assert result.method in ("proximal",)
        assert result.confidence > 0


# ── Name match resolution ─────────────────────────────────────────────────────

class TestNameMatchResolution:
    def test_partial_name_found(self):
        s = _session_with_entities("MacBook Air", "Dell XPS")
        result = reference_resolver.resolve("Tell me more about MacBook Air", s)
        assert result.method == "name_match"
        assert result.entity_name == "MacBook Air"
        assert result.confidence >= 0.9


# ── No-match cases ────────────────────────────────────────────────────────────

class TestNoMatch:
    def test_empty_session_returns_none(self):
        s = CognitiveSession(conversation_id=str(uuid.uuid4()))
        result = reference_resolver.resolve("What is this?", s)
        assert result.method == "none"
        assert result.entity_id is None
        assert result.confidence == 0.0

    def test_unambiguous_question_returns_none(self):
        s = _session_with_entities("MacBook Air")
        result = reference_resolver.resolve("What is the capital of France?", s)
        assert result.method == "none"


# ── has_reference ─────────────────────────────────────────────────────────────

class TestHasReference:
    def test_detects_it(self):
        assert reference_resolver.has_reference("Research it now") is True

    def test_detects_first(self):
        assert reference_resolver.has_reference("Show the first one") is True

    def test_no_reference_in_plain_question(self):
        assert reference_resolver.has_reference("What is FastAPI?") is False

    def test_detects_those(self):
        assert reference_resolver.has_reference("Compare those products") is True


# ── resolve_all ───────────────────────────────────────────────────────────────

class TestResolveAll:
    def test_resolve_all_multiple_ordinals(self):
        s = _session_with_entities("A", "B", "C")
        results = reference_resolver.resolve_all("compare the first and second", s)
        names = [r.entity_name for r in results if r.entity_name]
        assert "A" in names
        assert "B" in names

    def test_resolve_all_no_entities(self):
        s = CognitiveSession(conversation_id=str(uuid.uuid4()))
        results = reference_resolver.resolve_all("What is it?", s)
        assert len(results) == 1
        assert results[0].method == "none"
