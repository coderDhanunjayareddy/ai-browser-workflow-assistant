"""
V2.5 BUG-05 unit tests — Suggested Follow-up Questions.
Covers: followup_service internals, integration with summarize and ask branches.
All LLM calls are mocked.
"""
import uuid
from unittest.mock import patch

from app.schemas.assist import ReadView, AssistRequest


# ── Helpers ───────────────────────────────────────────────────────────────────

_THREE_QUESTIONS = (
    "What technology does this framework use?\n"
    "How does the installation process work?\n"
    "What are the main performance characteristics?"
)

def _make_request(message: str = "what is this page about?", **rv_kwargs) -> AssistRequest:
    defaults = dict(
        url="https://example.com",
        title="Example Page",
        visible_text="FastAPI is a high-performance Python web framework. Install with pip install fastapi.",
    )
    defaults.update(rv_kwargs)
    return AssistRequest(
        conversation_id=str(uuid.uuid4()),
        message=message,
        read_view=ReadView(**defaults),
        context_fingerprint="test-fp",
        selection_scope="page",
    )


def _reset():
    from app.conversation import manager as conversation_manager
    conversation_manager._reset_store_for_testing()


# ── FollowupService internals ─────────────────────────────────────────────────

class TestFollowupServiceParse:
    def test_plain_lines_parsed(self):
        from app.services.followup_service import _parse
        raw = "What does this do?\nHow is it installed?\nWho maintains it?"
        result = _parse(raw)
        assert result == [
            "What does this do?",
            "How is it installed?",
            "Who maintains it?",
        ]

    def test_numbered_prefix_stripped(self):
        from app.services.followup_service import _parse
        raw = "1. What does this do?\n2. How is it installed?\n3. Who maintains it?"
        result = _parse(raw)
        assert result == [
            "What does this do?",
            "How is it installed?",
            "Who maintains it?",
        ]

    def test_bullet_prefix_stripped(self):
        from app.services.followup_service import _parse
        raw = "- What does this do?\n- How is it installed?\n- Who maintains it?"
        result = _parse(raw)
        assert all(not q.startswith("-") for q in result)

    def test_dash_unicode_bullet_stripped(self):
        from app.services.followup_service import _parse
        raw = "– What is the price?\n– Who wrote this?\n– When was it published?"
        result = _parse(raw)
        assert all(q[0].isupper() or q[0].isdigit() for q in result)

    def test_empty_lines_ignored(self):
        from app.services.followup_service import _parse
        raw = "\nWhat does this do?\n\nHow is it installed?\n\nWho maintains it?\n"
        result = _parse(raw)
        assert len(result) == 3

    def test_capped_at_max_followups(self):
        from app.services.followup_service import _parse, _MAX_FOLLOWUPS
        raw = "\n".join(f"Question number {i}?" for i in range(10))
        result = _parse(raw)
        assert len(result) == _MAX_FOLLOWUPS

    def test_empty_raw_returns_empty(self):
        from app.services.followup_service import _parse
        assert _parse("") == []
        assert _parse("   \n  \n  ") == []


class TestFollowupServiceFilter:
    def test_clean_question_passes(self):
        from app.services.followup_service import _is_clean
        assert _is_clean("What technology does this page describe?") is True

    def test_research_keyword_blocked(self):
        from app.services.followup_service import _is_clean
        assert _is_clean("Can you research this topic further?") is False

    def test_summarize_keyword_blocked(self):
        from app.services.followup_service import _is_clean
        assert _is_clean("Can you summarize the second section?") is False

    def test_compare_keyword_blocked(self):
        from app.services.followup_service import _is_clean
        assert _is_clean("How does this compare to other frameworks?") is False

    def test_versus_keyword_blocked(self):
        from app.services.followup_service import _is_clean
        assert _is_clean("React versus Vue — which is mentioned?") is False

    def test_look_up_blocked(self):
        from app.services.followup_service import _is_clean
        assert _is_clean("Can you look up the author's background?") is False

    def test_which_is_better_blocked(self):
        from app.services.followup_service import _is_clean
        assert _is_clean("Which is better according to this page?") is False


class TestFollowupServiceGenerate:
    def test_returns_list_of_strings(self):
        from app.services.followup_service import generate
        with patch("app.services.ai_service.generate_text", return_value=_THREE_QUESTIONS):
            result = generate("Some page content", "User asked about the page.")
        assert isinstance(result, list)
        assert all(isinstance(q, str) for q in result)

    def test_returns_up_to_three(self):
        from app.services.followup_service import generate
        with patch("app.services.ai_service.generate_text", return_value=_THREE_QUESTIONS):
            result = generate("Content", "Context")
        assert len(result) <= 3

    def test_page_content_in_prompt(self):
        from app.services.followup_service import generate
        captured: list[str] = []
        def cap(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return _THREE_QUESTIONS
        with patch("app.services.ai_service.generate_text", side_effect=cap):
            generate("Unique page content abc123", "Some context")
        assert "Unique page content abc123" in captured[0]
        assert "PAGE CONTENT:" in captured[0]

    def test_context_in_prompt(self):
        from app.services.followup_service import generate
        captured: list[str] = []
        def cap(system_prompt: str, user_message: str) -> str:
            captured.append(user_message)
            return _THREE_QUESTIONS
        with patch("app.services.ai_service.generate_text", side_effect=cap):
            generate("Content", "User asked: What is Python?")
        assert "User asked: What is Python?" in captured[0]
        assert "RECENT INTERACTION:" in captured[0]

    def test_llm_exception_returns_empty_list(self):
        from app.services.followup_service import generate
        with patch("app.services.ai_service.generate_text", side_effect=RuntimeError("API down")):
            result = generate("Content", "Context")
        assert result == []

    def test_empty_llm_response_returns_empty_list(self):
        from app.services.followup_service import generate
        with patch("app.services.ai_service.generate_text", return_value=""):
            result = generate("Content", "Context")
        assert result == []

    def test_trigger_words_filtered_from_output(self):
        from app.services.followup_service import generate
        polluted = "How does this compare to React?\nWhat is the install command?\nWho maintains this?"
        with patch("app.services.ai_service.generate_text", return_value=polluted):
            result = generate("Content", "Context")
        assert not any("compare" in q.lower() for q in result)

    def test_system_prompt_mentions_trigger_words(self):
        from app.services.followup_service import _SYSTEM_PROMPT
        assert "research" in _SYSTEM_PROMPT
        assert "compare" in _SYSTEM_PROMPT
        assert "summarize" in _SYSTEM_PROMPT

    def test_max_followups_constant_is_three(self):
        from app.services.followup_service import _MAX_FOLLOWUPS
        assert _MAX_FOLLOWUPS == 3


# ── Integration: follow-ups in summarize response ─────────────────────────────

class TestFollowupsInSummarize:
    def _mock_summary_json(self) -> str:
        import json
        return json.dumps({
            "tldr": "FastAPI is a fast Python web framework.",
            "key_points": ["High performance", "Easy to use"],
            "entities": [],
            "available_actions": ["Install FastAPI"],
        })

    def test_summarize_response_has_followups(self):
        _reset()
        from app.assist.ambient_assistant import run
        request = _make_request(message="summarize this page")
        with patch("app.services.ai_service.generate_text",
                   side_effect=[self._mock_summary_json(), _THREE_QUESTIONS]):
            resp = run(request)
        assert len(resp.suggested_followups) > 0

    def test_summarize_followups_are_strings(self):
        _reset()
        from app.assist.ambient_assistant import run
        request = _make_request(message="summarize this page")
        with patch("app.services.ai_service.generate_text",
                   side_effect=[self._mock_summary_json(), _THREE_QUESTIONS]):
            resp = run(request)
        assert all(isinstance(q, str) for q in resp.suggested_followups)

    def test_summarize_followups_count(self):
        _reset()
        from app.assist.ambient_assistant import run
        request = _make_request(message="summarize this page")
        with patch("app.services.ai_service.generate_text",
                   side_effect=[self._mock_summary_json(), _THREE_QUESTIONS]):
            resp = run(request)
        assert 1 <= len(resp.suggested_followups) <= 3

    def test_summarize_tldr_used_as_context(self):
        _reset()
        from app.assist.ambient_assistant import run
        captured_followup_prompts: list[str] = []
        def cap(system_prompt: str, user_message: str) -> str:
            captured_followup_prompts.append(user_message)
            return _THREE_QUESTIONS

        request = _make_request(message="summarize this page")
        with patch("app.services.ai_service.generate_text",
                   side_effect=[self._mock_summary_json()]):
            with patch("app.services.followup_service.generate", wraps=None) as mock_gen:
                mock_gen.return_value = []
                run(request)
        # Confirm followup_service.generate was called with TL;DR in context
        assert mock_gen.called
        _, call_kwargs = mock_gen.call_args
        assert "FastAPI is a fast Python web framework." in call_kwargs.get("context", "")

    def test_summarize_followup_failure_does_not_affect_summary(self):
        _reset()
        from app.assist.ambient_assistant import run
        request = _make_request(message="summarize this page")
        with patch("app.services.ai_service.generate_text",
                   return_value=self._mock_summary_json()):
            with patch("app.services.followup_service.generate",
                       side_effect=RuntimeError("follow-up failed")):
                # followup_service.generate already swallows exceptions; this
                # tests that even if it doesn't, ambient_assistant handles it
                resp = run(request)
        # Primary summary must still be present regardless of follow-up failure
        assert resp.type == "summary"
        assert resp.intent == "summarize"


# ── Integration: follow-ups in ask response ───────────────────────────────────

class TestFollowupsInAsk:
    def test_ask_response_has_no_followups(self):
        """Option B: ask responses always return suggested_followups=[]."""
        _reset()
        from app.assist.ambient_assistant import run
        request = _make_request(message="what is this page about?")
        with patch("app.services.ai_service.generate_text",
                   return_value="FastAPI is a Python web framework."):
            resp = run(request)
        assert resp.suggested_followups == []

    def test_ask_followups_is_empty_list(self):
        _reset()
        from app.assist.ambient_assistant import run
        request = _make_request(message="what is this page about?")
        with patch("app.services.ai_service.generate_text", return_value="Some answer."):
            resp = run(request)
        assert isinstance(resp.suggested_followups, list)
        assert len(resp.suggested_followups) == 0

    def test_ask_does_not_call_followup_service(self):
        """followup_service.generate must never be called on the ask path (Option B)."""
        _reset()
        from app.assist.ambient_assistant import run
        request = _make_request(message="how do I install FastAPI?")

        with patch("app.services.ai_service.generate_text",
                   return_value="Run pip install fastapi."):
            with patch("app.services.followup_service.generate") as mock_gen:
                run(request)

        assert not mock_gen.called

    def test_ask_answer_returned_without_followup_overhead(self):
        """Primary answer content is unaffected — no follow-up side effects."""
        _reset()
        from app.assist.ambient_assistant import run
        request = _make_request(message="what is this page about?")
        with patch("app.services.ai_service.generate_text", return_value="FastAPI is great."):
            resp = run(request)
        assert resp.type == "answer"
        assert resp.content == "FastAPI is great."
        assert resp.suggested_followups == []

    def test_not_implemented_fallback_unchanged(self):
        """The fallback 'not_implemented' branch has its own static follow-up — must not change."""
        _reset()
        from app.assist.ambient_assistant import run
        request = _make_request(message="book me a flight")
        with patch("app.services.followup_service.generate", return_value=[]):
            resp = run(request)
        assert resp.type == "not_implemented"
        assert "Summarize this page" in resp.suggested_followups
