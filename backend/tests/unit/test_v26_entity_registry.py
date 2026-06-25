"""Unit tests for cognitive_core.entity_registry."""
import uuid

import pytest

from app.cognitive_core.models import CognitiveSession, EntityType
from app.cognitive_core import entity_registry


def _session() -> CognitiveSession:
    return CognitiveSession(conversation_id=str(uuid.uuid4()))


# ── extract_from_summary_entities ────────────────────────────────────────────

class TestExtractFromSummaryEntities:
    def test_basic_product_entity(self):
        s = _session()
        entities = entity_registry.extract_from_summary_entities(
            s,
            [{"label": "Product", "value": "MacBook Air"}],
            turn=1,
        )
        assert len(entities) == 1
        assert entities[0].name == "MacBook Air"
        assert entities[0].type == EntityType.product
        assert entities[0].confidence == 0.9

    def test_multiple_entities(self):
        s = _session()
        entities = entity_registry.extract_from_summary_entities(
            s,
            [
                {"label": "Product", "value": "MacBook Air"},
                {"label": "Brand", "value": "Apple"},
                {"label": "Price", "value": "$1099"},
            ],
            turn=1,
        )
        assert len(entities) == 3
        names = [e.name for e in entities]
        assert "MacBook Air" in names
        assert "Apple" in names

    def test_empty_value_skipped(self):
        s = _session()
        entities = entity_registry.extract_from_summary_entities(
            s,
            [{"label": "Product", "value": ""}],
            turn=1,
        )
        assert len(entities) == 0

    def test_entity_stored_in_session(self):
        s = _session()
        entity_registry.extract_from_summary_entities(
            s, [{"label": "Product", "value": "Dell XPS"}], turn=1
        )
        assert len(s.active_entities) == 1
        entity = list(s.active_entities.values())[0]
        assert entity.name == "Dell XPS"

    def test_duplicate_entity_merged(self):
        s = _session()
        entity_registry.extract_from_summary_entities(
            s, [{"label": "Product", "value": "MacBook Air"}], turn=1
        )
        entity_registry.extract_from_summary_entities(
            s, [{"label": "Device", "value": "MacBook Air"}], turn=2
        )
        assert len(s.active_entities) == 1  # no duplicate

    def test_label_type_inference_flight(self):
        s = _session()
        entities = entity_registry.extract_from_summary_entities(
            s, [{"label": "Airline", "value": "IndiGo"}], turn=1
        )
        assert entities[0].type == EntityType.flight

    def test_label_type_inference_hotel(self):
        s = _session()
        entities = entity_registry.extract_from_summary_entities(
            s, [{"label": "Hotel", "value": "Marriott"}], turn=1
        )
        assert entities[0].type == EntityType.hotel

    def test_unknown_label_becomes_generic(self):
        s = _session()
        entities = entity_registry.extract_from_summary_entities(
            s, [{"label": "Misc", "value": "SomeEntity"}], turn=1
        )
        assert entities[0].type == EntityType.generic

    def test_source_turn_recorded(self):
        s = _session()
        entities = entity_registry.extract_from_summary_entities(
            s, [{"label": "Product", "value": "Pixel 8"}], turn=5
        )
        assert entities[0].source_turn == 5


# ── extract_from_message ─────────────────────────────────────────────────────

class TestExtractFromMessage:
    def test_compare_and_pattern(self):
        s = _session()
        entities = entity_registry.extract_from_message(
            s, "compare MacBook Air and Dell XPS", turn=1
        )
        names = [e.name for e in entities]
        assert "MacBook Air" in names
        assert "Dell XPS" in names

    def test_vs_pattern(self):
        s = _session()
        entities = entity_registry.extract_from_message(
            s, "iPhone 15 vs Samsung Galaxy S24", turn=1
        )
        names = [e.name for e in entities]
        assert any("iPhone" in n for n in names)
        assert any("Samsung" in n for n in names)

    def test_brand_keyword_detection(self):
        s = _session()
        entities = entity_registry.extract_from_message(
            s, "tell me about the MacBook", turn=1
        )
        # Should detect "macbook" brand keyword
        assert len(entities) >= 1

    def test_no_entities_for_generic_question(self):
        s = _session()
        entities = entity_registry.extract_from_message(
            s, "what is this page about?", turn=1
        )
        assert len(entities) == 0

    def test_entities_added_to_session(self):
        s = _session()
        entity_registry.extract_from_message(
            s, "compare iPhone and Samsung", turn=1
        )
        assert len(s.active_entities) >= 2

    def test_entity_order_tracked(self):
        s = _session()
        entity_registry.extract_from_message(
            s, "compare iPhone and Samsung", turn=1
        )
        assert len(s.entity_order) >= 2


# ── get_ordered_entities ─────────────────────────────────────────────────────

class TestGetOrderedEntities:
    def test_returns_in_insertion_order(self):
        s = _session()
        entity_registry.extract_from_summary_entities(
            s, [{"label": "Product", "value": "First"}], turn=1
        )
        entity_registry.extract_from_summary_entities(
            s, [{"label": "Product", "value": "Second"}], turn=2
        )
        ordered = entity_registry.get_ordered_entities(s)
        assert ordered[0].name == "First"
        assert ordered[1].name == "Second"

    def test_eviction_at_max_capacity(self):
        s = _session()
        for i in range(entity_registry.MAX_ENTITIES + 2):
            entity_registry.extract_from_summary_entities(
                s, [{"label": "Product", "value": f"Entity{i}"}], turn=i
            )
        assert len(s.active_entities) <= entity_registry.MAX_ENTITIES
