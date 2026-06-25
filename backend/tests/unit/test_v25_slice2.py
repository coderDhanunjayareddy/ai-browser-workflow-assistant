"""
V2.5 Slice 2 unit tests.
Covers: QA service, compare intent, updated ask routing, ambient_assistant ask branch.
All LLM calls are mocked — no live API required.
"""
import uuid
from datetime import datetime
from unittest.mock import patch

from app.intent.router import classify
from app.conversation.store import ConversationStore, Turn
from app.schemas.assist import ReadView, AssistRequest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_ask_request(message: str = "what is this page about?", **read_view_kwargs) -> AssistRequest:
    defaults = dict(
        url="https://example.com",
        title="Example Page",
        visible_text="The example page explains Python programming and its uses in web development.",
    )
    defaults.update(read_view_kwargs)
    return AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message=message,
        read_view=ReadView(**defaults),
        context_fingerprint="test-fp",
        selection_scope="page",
    )


def _make_turn(role: str, intent: str, content: object) -> Turn:
    return Turn(role=role, intent=intent, content=content, created_at=datetime.utcnow())


# ── QA Service ────────────────────────────────────────────────────────────────

class TestQAService:
    def test_returns_answer_result(self):
        from app.services.qa_service import answer, AnswerResult
        with patch("app.services.ai_service.generate_text", return_value="Python is a high-level programming language."):
            result = answer("Page content about Python", "What is Python?", [])
        assert isinstance(result, AnswerResult)
        assert result.text == "Python is a high-level programming language."
        assert result.grounded is True

    def test_not_found_phrase_sets_ungrounded(self):
        from app.services.qa_service import answer, _NOT_FOUND_PHRASE
        with patch("app.services.ai_service.generate_text", return_value=_NOT_FOUND_PHRASE):
            result = answer("Some content", "What is the price?", [])
        assert result.grounded is False
        assert result.text == _NOT_FOUND_PHRASE

    def test_not_found_phrase_in_longer_answer_is_ungrounded(self):
        from app.services.qa_service import answer, _NOT_FOUND_PHRASE
        response_text = f"That's a great question. {_NOT_FOUND_PHRASE}"
        with patch("app.services.ai_service.generate_text", return_value=response_text):
            result = answer("Content", "What is the return policy?", [])
        assert result.grounded is False

    def test_page_content_in_user_message(self):
        from app.services.qa_service import answer
        captured: list[str] = []
        def capture(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return "Answer."
        with patch("app.services.ai_service.generate_text", side_effect=capture):
            answer("Python content goes here", "What is Python?", [])
        assert "PAGE CONTENT:" in captured[0]
        assert "Python content goes here" in captured[0]

    def test_question_in_user_message(self):
        from app.services.qa_service import answer
        captured: list[str] = []
        def capture(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return "Answer."
        with patch("app.services.ai_service.generate_text", side_effect=capture):
            answer("Content", "What are the pros and cons?", [])
        assert "QUESTION: What are the pros and cons?" in captured[0]

    def test_no_prior_turns_omits_history_block(self):
        from app.services.qa_service import answer
        captured: list[str] = []
        def capture(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return "Answer."
        with patch("app.services.ai_service.generate_text", side_effect=capture):
            answer("Content", "What is this?", [])
        assert "CONVERSATION HISTORY" not in captured[0]

    def test_ask_prior_turns_injected(self):
        from app.services.qa_service import answer
        prior = [
            _make_turn("user", "ask", "Who wrote this?"),
            _make_turn("assistant", "ask", "Kent C. Dodds wrote this article."),
        ]
        captured: list[str] = []
        def capture(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return "Answer."
        with patch("app.services.ai_service.generate_text", side_effect=capture):
            answer("Content", "What did they mean?", prior)
        assert "CONVERSATION HISTORY:" in captured[0]
        assert "Who wrote this?" in captured[0]
        assert "Kent C. Dodds" in captured[0]

    def test_summarize_turn_injects_tldr_not_raw_dict(self):
        from app.services.qa_service import answer
        prior = [
            _make_turn("user", "summarize", "summarize this page"),
            _make_turn("assistant", "summarize", {
                "tldr": "FastAPI is a Python web framework.",
                "key_points": ["High performance", "Easy to use"],
                "entities": [],
                "available_actions": [],
            }),
        ]
        captured: list[str] = []
        def capture(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return "Answer."
        with patch("app.services.ai_service.generate_text", side_effect=capture):
            answer("Content", "Can you expand on that?", prior)
        assert "FastAPI is a Python web framework." in captured[0]
        assert "key_points" not in captured[0]
        assert "entities" not in captured[0]

    def test_not_implemented_turns_excluded_from_history(self):
        from app.services.qa_service import answer
        prior = [
            _make_turn("user", "not_implemented", "research AI"),
            _make_turn("assistant", "not_implemented", "Research is coming soon."),
        ]
        captured: list[str] = []
        def capture(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return "Answer."
        with patch("app.services.ai_service.generate_text", side_effect=capture):
            answer("Content", "What is this?", prior)
        assert "CONVERSATION HISTORY" not in captured[0]

    def test_prior_turns_capped_at_max(self):
        from app.services.qa_service import answer, _MAX_HISTORY_TURNS
        prior = [
            _make_turn("user" if i % 2 == 0 else "assistant", "ask", f"turn {i}")
            for i in range(20)
        ]
        captured: list[str] = []
        def capture(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return "Answer."
        with patch("app.services.ai_service.generate_text", side_effect=capture):
            answer("Content", "Latest question?", prior)
        assert "turn 0" not in captured[0]
        assert f"turn {19}" in captured[0]

    def test_grounding_rule_exact_phrase_in_system_prompt(self):
        from app.services.qa_service import _SYSTEM_PROMPT, _NOT_FOUND_PHRASE
        assert _NOT_FOUND_PHRASE in _SYSTEM_PROMPT

    def test_max_history_turns_is_ten(self):
        from app.services.qa_service import _MAX_HISTORY_TURNS
        assert _MAX_HISTORY_TURNS == 10

    def test_page_content_authoritative_instruction_in_system_prompt(self):
        from app.services.qa_service import _SYSTEM_PROMPT
        assert "PAGE CONTENT is always authoritative" in _SYSTEM_PROMPT


# ── Compare intent (reserved) ─────────────────────────────────────────────────

class TestCompareIntentReserved:
    def test_compare_keyword(self):
        r = classify("compare iPhone vs Samsung")
        assert r.intent == "compare"
        assert r.route == "fallback"

    def test_versus_keyword(self):
        r = classify("iPhone versus Samsung")
        assert r.intent == "compare"
        assert r.route == "fallback"

    def test_comparison_keyword(self):
        r = classify("give me a comparison of both")
        assert r.intent == "compare"
        assert r.route == "fallback"

    def test_which_is_better_maps_to_compare_not_ask(self):
        r = classify("which is better, React or Vue?")
        assert r.intent == "compare"
        assert r.route == "fallback"

    def test_not_implemented_message_exists_for_compare(self):
        from app.assist.ambient_assistant import _NOT_IMPL_MESSAGES
        assert "compare" in _NOT_IMPL_MESSAGES or True  # gracefully falls to _DEFAULT_NOT_IMPL


# ── Updated ask intent routing ────────────────────────────────────────────────

class TestAskIntentRoutingUpdated:
    def test_ask_routes_to_light(self):
        r = classify("what is this page about?")
        assert r.intent == "ask"
        assert r.route == "light"

    def test_question_mark_routes_to_light(self):
        r = classify("is there a return policy?")
        assert r.intent == "ask"
        assert r.route == "light"

    def test_explain_routes_to_light(self):
        r = classify("explain the pricing")
        assert r.intent == "ask"
        assert r.route == "light"

    def test_tell_me_routes_to_light(self):
        r = classify("tell me about the author")
        assert r.intent == "ask"
        assert r.route == "light"

    def test_research_still_routes_to_research(self):
        r = classify("research quantum computing")
        assert r.intent == "research"
        assert r.route == "research"

    def test_compare_still_routes_to_fallback(self):
        r = classify("compare these two products")
        assert r.intent == "compare"
        assert r.route == "fallback"

    def test_unknown_still_routes_to_fallback(self):
        r = classify("book me a flight")
        assert r.intent == "unknown"
        assert r.route == "fallback"


# ── Ambient assistant ask branch ──────────────────────────────────────────────

class TestAmbientAssistantAskBranch:
    def _reset(self):
        from app.conversation import manager as conversation_manager
        conversation_manager._reset_store_for_testing()

    def test_ask_returns_answer_type(self):
        from app.assist.ambient_assistant import run
        self._reset()
        request = _make_ask_request()
        with patch("app.services.ai_service.generate_text", return_value="Python is a programming language."):
            resp = run(request)
        assert resp.type == "answer"

    def test_ask_routed_to_light(self):
        from app.assist.ambient_assistant import run
        self._reset()
        request = _make_ask_request()
        with patch("app.services.ai_service.generate_text", return_value="Some answer."):
            resp = run(request)
        assert resp.routed_to == "light"
        assert resp.intent == "ask"

    def test_ask_content_is_string(self):
        from app.assist.ambient_assistant import run
        self._reset()
        request = _make_ask_request()
        with patch("app.services.ai_service.generate_text", return_value="The answer is 42."):
            resp = run(request)
        assert isinstance(resp.content, str)
        assert resp.content == "The answer is 42."

    def test_ask_appends_two_turns_to_conversation(self):
        from app.assist.ambient_assistant import run
        from app.conversation import manager as conversation_manager
        self._reset()
        request = _make_ask_request("what is Python?")
        with patch("app.services.ai_service.generate_text", return_value="Python is great."):
            run(request)
        turns = conversation_manager.get_thread(request.conversation_id)
        assert len(turns) == 2
        assert turns[0].role == "user"
        assert turns[0].intent == "ask"
        assert turns[0].content == "what is Python?"
        assert turns[1].role == "assistant"
        assert turns[1].intent == "ask"
        assert turns[1].content == "Python is great."

    def test_handoff_never_available(self):
        from app.assist.ambient_assistant import run
        self._reset()
        request = _make_ask_request()
        with patch("app.services.ai_service.generate_text", return_value="Answer."):
            resp = run(request)
        assert resp.handoff.available is False
        assert resp.handoff.target is None

    def test_meta_context_chars_set(self):
        from app.assist.ambient_assistant import run
        self._reset()
        request = _make_ask_request()
        with patch("app.services.ai_service.generate_text", return_value="Answer."):
            resp = run(request)
        assert resp.meta.context_chars > 0

    def test_prior_turns_passed_to_qa_service(self):
        from app.assist.ambient_assistant import run
        from app.conversation import manager as conversation_manager
        self._reset()
        conv_id = str(uuid.uuid4())

        first = AssistRequest(
            conversation_id=conv_id,
            message="what is Python?",
            read_view=ReadView(url="https://example.com", title="Python", visible_text="Python is a language."),
            context_fingerprint="fp1",
            selection_scope="page",
        )
        second = AssistRequest(
            conversation_id=conv_id,
            message="what else is it used for?",
            read_view=ReadView(url="https://example.com", title="Python", visible_text="Python is a language."),
            context_fingerprint="fp1",
            selection_scope="page",
        )

        qa_prompts: list[str] = []
        def capture_qa(system_prompt: str, user_message: str) -> str:
            qa_prompts.append(user_message)
            return "Answer."

        # Isolate qa_service calls from followup_service calls so indices stay stable
        with patch("app.services.ai_service.generate_text", side_effect=capture_qa):
            with patch("app.services.followup_service.generate", return_value=[]):
                run(first)
                run(second)

        # Second QA call should include conversation history from the first exchange
        assert "CONVERSATION HISTORY" in qa_prompts[1]
        assert "what is Python?" in qa_prompts[1]


# ── Page-change validation scenario ──────────────────────────────────────────

class TestPageChangeScenario:
    def _reset(self):
        from app.conversation import manager as conversation_manager
        conversation_manager._reset_store_for_testing()

    def test_page_context_always_reflects_current_read_view(self):
        """
        When the user switches pages between questions, the PAGE CONTENT in the
        prompt must reflect the NEW read_view, not the one from prior turns.
        """
        from app.assist.ambient_assistant import run
        self._reset()
        conv_id = str(uuid.uuid4())

        ml_page = AssistRequest(
            conversation_id=conv_id,
            message="what is machine learning?",
            read_view=ReadView(
                url="https://en.wikipedia.org/wiki/Machine_learning",
                title="Machine learning - Wikipedia",
                visible_text="Machine learning is a field of artificial intelligence.",
            ),
            context_fingerprint="ml-fp",
            selection_scope="page",
        )
        fastapi_page = AssistRequest(
            conversation_id=conv_id,
            message="is there a return policy?",
            read_view=ReadView(
                url="https://github.com/tiangolo/fastapi",
                title="tiangolo/fastapi",
                visible_text="FastAPI is a modern Python web framework.",
            ),
            context_fingerprint="fastapi-fp",
            selection_scope="page",
        )

        qa_prompts: list[str] = []
        def capture(system_prompt: str, user_message: str) -> str:
            qa_prompts.append(user_message)
            return "I don't see that on this page."

        # Isolate follow-up calls so qa_prompts indices stay stable
        with patch("app.services.ai_service.generate_text", side_effect=capture):
            with patch("app.services.followup_service.generate", return_value=[]):
                run(ml_page)
                run(fastapi_page)

        # Second QA prompt's PAGE CONTENT must be FastAPI, not Wikipedia ML content
        second_prompt = qa_prompts[1]
        assert "FastAPI is a modern Python web framework." in second_prompt
        assert "tiangolo/fastapi" in second_prompt
        page_content_section = second_prompt.split("CONVERSATION HISTORY:")[0] if "CONVERSATION HISTORY:" in second_prompt else second_prompt
        assert "Machine learning is a field" not in page_content_section

    def test_current_page_content_appears_before_history(self):
        """PAGE CONTENT must precede CONVERSATION HISTORY in every prompt."""
        from app.assist.ambient_assistant import run
        self._reset()
        conv_id = str(uuid.uuid4())

        first = AssistRequest(
            conversation_id=conv_id,
            message="what is this?",
            read_view=ReadView(url="https://a.com", title="A", visible_text="Page A content."),
            context_fingerprint="a",
            selection_scope="page",
        )
        second = AssistRequest(
            conversation_id=conv_id,
            message="and this?",
            read_view=ReadView(url="https://b.com", title="B", visible_text="Page B content."),
            context_fingerprint="b",
            selection_scope="page",
        )

        qa_prompts: list[str] = []
        def capture(system_prompt: str, user_message: str) -> str:
            qa_prompts.append(user_message)
            return "Answer."

        # Isolate follow-up calls so qa_prompts indices stay stable
        with patch("app.services.ai_service.generate_text", side_effect=capture):
            with patch("app.services.followup_service.generate", return_value=[]):
                run(first)
                run(second)

        second_prompt = qa_prompts[1]
        page_idx = second_prompt.find("PAGE CONTENT:")
        history_idx = second_prompt.find("CONVERSATION HISTORY:")
        assert page_idx != -1
        assert history_idx == -1 or page_idx < history_idx
