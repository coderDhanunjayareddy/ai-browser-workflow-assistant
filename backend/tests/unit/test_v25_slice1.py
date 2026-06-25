"""
V2.5 Slice 1 unit tests.
Covers: Intent Router, CTCE, ConversationStore, SummarizationService, schema shapes.
All LLM calls are mocked — no live API required.
"""
import json
from unittest.mock import patch

from app.intent.router import classify
from app.context.tab_context_engine import format_read_view
from app.schemas.assist import ReadView, StructuredSummary, AssistHandoff, AssistMeta, AssistResponse
from app.conversation.store import ConversationStore, MAX_CONVERSATIONS, MAX_TURNS_PER_CONVERSATION


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_read_view(**kwargs) -> ReadView:
    defaults = dict(
        url="https://example.com",
        title="Example Page",
        headings=["H1 Heading", "H2 Subheading"],
        content_blocks=[{"selector": ".main", "text": "Main content here."}],
        visible_text="This is the visible text on the page.",
        selected_text="",
        metadata={"description": "A test page"},
    )
    defaults.update(kwargs)
    return ReadView(**defaults)


def _mock_llm_json(tldr="Test summary", key_points=None, entities=None, available_actions=None) -> str:
    return json.dumps({
        "tldr": tldr,
        "key_points": key_points or ["Point 1", "Point 2"],
        "entities": entities or [{"label": "Price", "value": "$10"}],
        "available_actions": available_actions or ["Search", "Filter"],
    })


# ── Intent Router ─────────────────────────────────────────────────────────────

class TestIntentRouter:
    def test_summarize_keyword(self):
        r = classify("summarize this page")
        assert r.intent == "summarize"
        assert r.route == "light"

    def test_tldr(self):
        r = classify("tldr")
        assert r.intent == "summarize"
        assert r.route == "light"

    def test_summary_in_sentence(self):
        r = classify("give me a summary of this")
        assert r.intent == "summarize"
        assert r.route == "light"

    def test_brief_keyword(self):
        r = classify("brief overview please")
        assert r.intent == "summarize"
        assert r.route == "light"

    def test_overview_keyword(self):
        r = classify("overview")
        assert r.intent == "summarize"
        assert r.route == "light"

    def test_research_reserved(self):
        r = classify("research quantum computing")
        assert r.intent == "research"
        assert r.route == "research"

    def test_look_up_maps_to_research(self):
        r = classify("look up flight prices")
        assert r.intent == "research"
        assert r.route == "research"

    def test_ask_intent_routes_to_light(self):
        r = classify("what is on this page?")
        assert r.intent == "ask"
        assert r.route == "light"

    def test_question_mark_maps_to_ask(self):
        r = classify("is there a return policy?")
        assert r.intent == "ask"
        assert r.route == "light"

    def test_explain_maps_to_ask(self):
        r = classify("explain the pricing")
        assert r.intent == "ask"
        assert r.route == "light"

    def test_unknown_action_intent(self):
        r = classify("book a flight to goa")
        assert r.intent == "unknown"
        assert r.route == "fallback"

    def test_empty_message(self):
        r = classify("")
        assert r.intent == "unknown"
        assert r.route == "fallback"

    def test_confidence_and_tier(self):
        r = classify("summarize this")
        assert r.confidence == 1.0
        assert r.tier == "deterministic"

    def test_selection_scope_does_not_change_summarize(self):
        r = classify("summarize the selection", selection_scope="selection")
        assert r.intent == "summarize"
        assert r.route == "light"


# ── Current Tab Context Engine ────────────────────────────────────────────────

class TestTabContextEngine:
    def test_url_and_title_present(self):
        rv = _make_read_view()
        result = format_read_view(rv)
        assert "https://example.com" in result
        assert "Example Page" in result

    def test_headings_present(self):
        rv = _make_read_view()
        result = format_read_view(rv)
        assert "H1 Heading" in result

    def test_content_block_text_present(self):
        rv = _make_read_view()
        result = format_read_view(rv)
        assert "Main content here." in result

    def test_visible_text_present(self):
        rv = _make_read_view()
        result = format_read_view(rv)
        assert "This is the visible text" in result

    def test_no_interactive_elements_section(self):
        rv = _make_read_view()
        result = format_read_view(rv)
        assert "INTERACTIVE ELEMENTS" not in result

    def test_visible_text_schema_max_enforced(self):
        # ReadView enforces max_length=8000; client truncates before sending.
        from pydantic import ValidationError
        import pytest
        with pytest.raises(ValidationError):
            _make_read_view(visible_text="a" * 9000)

    def test_visible_text_full_budget_included(self):
        rv = _make_read_view(visible_text="b" * 8000)
        result = format_read_view(rv)
        assert "b" * 100 in result

    def test_selection_scope_uses_selected_text(self):
        rv = _make_read_view(
            visible_text="Full page text",
            selected_text="Only this part",
        )
        result = format_read_view(rv, selection_scope="selection")
        assert "Only this part" in result
        assert "SELECTED TEXT" in result

    def test_selection_scope_omits_full_page_text(self):
        rv = _make_read_view(
            visible_text="Full page text",
            selected_text="Only this part",
        )
        result = format_read_view(rv, selection_scope="selection")
        assert "Full page text" not in result

    def test_metadata_included(self):
        rv = _make_read_view(metadata={"description": "A great page"})
        result = format_read_view(rv)
        assert "A great page" in result

    def test_empty_selection_falls_back_to_page(self):
        rv = _make_read_view(visible_text="Page content", selected_text="")
        result = format_read_view(rv, selection_scope="selection")
        # No selected text → falls through to page content
        assert "Page content" in result


# ── ConversationStore ─────────────────────────────────────────────────────────

class TestConversationStore:
    def test_append_and_retrieve(self):
        store = ConversationStore()
        store.append_turn("c1", role="user", intent="summarize", content="hello")
        turns = store.get_turns("c1")
        assert len(turns) == 1
        assert turns[0].role == "user"
        assert turns[0].content == "hello"
        assert turns[0].intent == "summarize"

    def test_multiple_conversations_isolated(self):
        store = ConversationStore()
        store.append_turn("c1", role="user", intent="summarize", content="for c1")
        store.append_turn("c2", role="user", intent="ask", content="for c2")
        assert store.get_turns("c1")[0].content == "for c1"
        assert store.get_turns("c2")[0].content == "for c2"

    def test_unknown_conversation_returns_empty(self):
        store = ConversationStore()
        assert store.get_turns("nonexistent") == []

    def test_capacity_eviction(self):
        store = ConversationStore()
        for i in range(MAX_CONVERSATIONS + 1):
            store.append_turn(f"c{i}", role="user", intent="summarize", content=f"msg{i}")
        assert store.get_turns("c0") == []
        assert len(store.get_turns(f"c{MAX_CONVERSATIONS}")) == 1

    def test_turn_ring_limit(self):
        store = ConversationStore()
        for i in range(MAX_TURNS_PER_CONVERSATION + 5):
            store.append_turn("c1", role="user", intent="summarize", content=f"msg{i}")
        assert len(store.get_turns("c1")) == MAX_TURNS_PER_CONVERSATION

    def test_clear(self):
        store = ConversationStore()
        store.append_turn("c1", role="user", intent="summarize", content="x")
        store.clear()
        assert store.get_turns("c1") == []

    def test_turn_has_timestamp(self):
        store = ConversationStore()
        store.append_turn("c1", role="user", intent="summarize", content="x")
        turn = store.get_turns("c1")[0]
        assert turn.created_at is not None


# ── SummarizationService ──────────────────────────────────────────────────────

class TestSummarizationService:
    def test_returns_structured_summary(self):
        from app.services.summarization_service import summarize
        with patch("app.services.ai_service.generate_text", return_value=_mock_llm_json()):
            result = summarize("some page content")
        assert isinstance(result, StructuredSummary)
        assert result.tldr == "Test summary"
        assert len(result.key_points) == 2
        assert result.entities[0]["label"] == "Price"
        assert "Search" in result.available_actions

    def test_selection_scope_in_prompt(self):
        from app.services.summarization_service import summarize
        captured: list[str] = []

        def fake_generate(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return _mock_llm_json()

        with patch("app.services.ai_service.generate_text", side_effect=fake_generate):
            summarize("selected text content", selection_scope="selection")

        assert len(captured) == 1
        assert "SELECTED TEXT" in captured[0] or "selected" in captured[0].lower()

    def test_page_scope_in_prompt(self):
        from app.services.summarization_service import summarize
        captured: list[str] = []

        def fake_generate(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return _mock_llm_json()

        with patch("app.services.ai_service.generate_text", side_effect=fake_generate):
            summarize("full page content", selection_scope="page")

        assert "full page" in captured[0].lower() or "Summarize the full" in captured[0]

    def test_handles_markdown_fences(self):
        from app.services.summarization_service import summarize
        fenced = "```json\n" + _mock_llm_json(tldr="Fenced") + "\n```"
        with patch("app.services.ai_service.generate_text", return_value=fenced):
            result = summarize("content")
        assert result.tldr == "Fenced"

    def test_handles_json_embedded_in_prose(self):
        from app.services.summarization_service import summarize
        prose = "Here is my answer: " + _mock_llm_json(tldr="Embedded") + " That's all."
        with patch("app.services.ai_service.generate_text", return_value=prose):
            result = summarize("content")
        assert result.tldr == "Embedded"

    def test_fallback_on_invalid_json(self):
        from app.services.summarization_service import summarize
        with patch("app.services.ai_service.generate_text", return_value="not json at all"):
            result = summarize("content")
        assert isinstance(result, StructuredSummary)
        assert len(result.tldr) > 0  # graceful fallback, no exception


# ── Schema shapes ─────────────────────────────────────────────────────────────

class TestSchemaShapes:
    def test_handoff_shape(self):
        h = AssistHandoff(available=False, target=None)
        assert h.available is False
        assert h.target is None

    def test_handoff_default(self):
        h = AssistHandoff()
        assert h.available is False
        assert h.target is None

    def test_assist_meta_context_chars(self):
        m = AssistMeta(tokens=10, latency_ms=500, cache_hit=False, context_chars=1234)
        assert m.context_chars == 1234

    def test_assist_meta_defaults(self):
        m = AssistMeta()
        assert m.tokens == 0
        assert m.context_chars == 0
        assert m.cache_hit is False

    def test_full_response_serialization(self):
        resp = AssistResponse(
            conversation_id="test-uuid",
            intent="summarize",
            routed_to="light",
            type="summary",
            content="test",
            handoff=AssistHandoff(available=False, target=None),
            meta=AssistMeta(context_chars=512),
        )
        data = resp.model_dump()
        assert data["handoff"]["available"] is False
        assert data["handoff"]["target"] is None
        assert data["meta"]["context_chars"] == 512
        assert data["routed_to"] == "light"

    def test_not_implemented_response_shape(self):
        resp = AssistResponse(
            conversation_id="test-uuid",
            intent="ask",
            routed_to="fallback",
            type="not_implemented",
            content="Page Q&A coming soon.",
            suggested_followups=["Summarize this page"],
            handoff=AssistHandoff(available=False, target=None),
            meta=AssistMeta(),
        )
        data = resp.model_dump()
        assert data["type"] == "not_implemented"
        assert data["routed_to"] == "fallback"
        assert "Summarize this page" in data["suggested_followups"]
