"""
V3.5 Research Provider unit tests.

Tests PageContextProvider, DuckDuckGoProvider, and AIKnowledgeProvider in isolation.
HTTP calls and LLM calls are mocked — no real network traffic.
"""
import uuid
from unittest.mock import patch, MagicMock

import pytest

from app.research.models import SourceType, ResearchSource
from app.research.providers.base import SearchProvider
from app.research.providers.page_context import PageContextProvider, _build_snippet
from app.research.providers.duckduckgo import DuckDuckGoProvider
from app.research.providers.ai_knowledge import AIKnowledgeProvider
from app.schemas.assist import ReadView


def _make_read_view(visible_text: str = "Sample page text.", title: str = "Page", url: str = "https://example.com") -> ReadView:
    return ReadView(url=url, title=title, visible_text=visible_text)


# ── SearchProvider ABC ─────────────────────────────────────────────────────────

class TestSearchProviderABC:
    def test_page_context_has_name(self):
        p = PageContextProvider()
        assert p.name == "PageContextProvider"

    def test_ddg_has_name(self):
        p = DuckDuckGoProvider()
        assert p.name == "DuckDuckGoProvider"

    def test_ai_knowledge_has_name(self):
        p = AIKnowledgeProvider()
        assert p.name == "AIKnowledgeProvider"


# ── PageContextProvider ────────────────────────────────────────────────────────

class TestPageContextProvider:
    def test_search_raises_not_implemented(self):
        p = PageContextProvider()
        with pytest.raises(NotImplementedError):
            p.search("query")

    def test_search_page_empty_visible_text_returns_empty(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="")
        result = p.search_page("query", rv)
        assert result == []

    def test_search_page_returns_single_source(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="Some content.")
        result = p.search_page("test", rv)
        assert len(result) == 1

    def test_source_type_is_page_context(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="Content here.")
        result = p.search_page("q", rv)
        assert result[0].source_type == SourceType.page_context

    def test_credibility_score_is_0_9(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="Content here.")
        result = p.search_page("q", rv)
        assert result[0].credibility_score == 0.9

    def test_title_from_read_view(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="Text.", title="My Page")
        result = p.search_page("q", rv)
        assert result[0].title == "My Page"

    def test_url_from_read_view(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="Text.", url="https://mysite.com/page")
        result = p.search_page("q", rv)
        assert result[0].url == "https://mysite.com/page"

    def test_snippet_contains_visible_text(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="Unique visible content XYZ123.")
        result = p.search_page("q", rv)
        assert "Unique visible content XYZ123" in result[0].snippet

    def test_snippet_truncated_at_1500(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="A" * 3000)
        result = p.search_page("q", rv)
        assert len(result[0].snippet) <= 1500

    def test_source_id_is_uuid(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="Content.")
        result = p.search_page("q", rv)
        # Should not raise when parsing as UUID
        uuid.UUID(result[0].source_id)

    def test_fallback_title_when_empty(self):
        p = PageContextProvider()
        rv = _make_read_view(visible_text="Content.", title="")
        result = p.search_page("q", rv)
        assert result[0].title == "Current Page"


# ── DuckDuckGoProvider ─────────────────────────────────────────────────────────

class TestDuckDuckGoProvider:
    def _ddg_response(self, abstract: str = "", related: list = None, heading: str = "") -> dict:
        return {
            "AbstractText": abstract,
            "AbstractURL": "https://en.wikipedia.org/wiki/Test" if abstract else "",
            "AbstractSource": "Wikipedia",
            "Heading": heading,
            "RelatedTopics": related or [],
        }

    def test_empty_response_returns_empty_list(self):
        p = DuckDuckGoProvider()
        result = p._parse(self._ddg_response(), max_results=5)
        assert result == []

    def test_abstract_creates_web_source(self):
        p = DuckDuckGoProvider()
        data = self._ddg_response(abstract="Python is a programming language.", heading="Python")
        result = p._parse(data, max_results=5)
        assert len(result) == 1
        assert result[0].source_type == SourceType.web

    def test_abstract_credibility_0_8(self):
        p = DuckDuckGoProvider()
        data = self._ddg_response(abstract="Some abstract.", heading="Topic")
        result = p._parse(data, max_results=5)
        assert result[0].credibility_score == 0.8

    def test_abstract_uses_heading_as_title(self):
        p = DuckDuckGoProvider()
        data = self._ddg_response(abstract="Text.", heading="My Heading")
        result = p._parse(data, max_results=5)
        assert result[0].title == "My Heading"

    def test_related_topics_parsed(self):
        p = DuckDuckGoProvider()
        data = self._ddg_response(related=[
            {"Text": "Topic A - Description of topic A", "FirstURL": "https://ddg.gg/a"},
        ])
        result = p._parse(data, max_results=5)
        assert len(result) == 1
        assert result[0].credibility_score == 0.7

    def test_related_topic_title_extracted(self):
        p = DuckDuckGoProvider()
        data = self._ddg_response(related=[
            {"Text": "Quantum Physics - A branch of physics", "FirstURL": "https://ddg.gg/q"},
        ])
        result = p._parse(data, max_results=5)
        assert result[0].title == "Quantum Physics"

    def test_max_results_respected(self):
        p = DuckDuckGoProvider()
        related = [
            {"Text": f"Topic {i} - desc {i}", "FirstURL": f"https://ddg.gg/{i}"}
            for i in range(10)
        ]
        data = self._ddg_response(related=related)
        result = p._parse(data, max_results=3)
        assert len(result) <= 3

    def test_http_error_returns_empty_list(self):
        p = DuckDuckGoProvider()
        with patch("httpx.Client") as mock_client:
            mock_client.return_value.__enter__.return_value.get.side_effect = Exception("timeout")
            result = p.search("query")
        assert result == []

    def test_related_topic_without_text_skipped(self):
        p = DuckDuckGoProvider()
        data = self._ddg_response(related=[
            {"Text": "", "FirstURL": "https://ddg.gg/x"},
        ])
        result = p._parse(data, max_results=5)
        assert result == []

    def test_non_dict_related_topic_skipped(self):
        p = DuckDuckGoProvider()
        data = self._ddg_response(related=["not_a_dict"])
        result = p._parse(data, max_results=5)
        assert result == []

    def test_snippet_truncated(self):
        p = DuckDuckGoProvider()
        long_text = "Word " * 500
        data = self._ddg_response(abstract=long_text, heading="Topic")
        result = p._parse(data, max_results=5)
        assert len(result[0].snippet) <= 600


# ── AIKnowledgeProvider ────────────────────────────────────────────────────────

class TestAIKnowledgeProvider:
    def _mock_llm(self, items: list) -> str:
        import json
        return json.dumps(items)

    def test_returns_sources_on_valid_response(self):
        p = AIKnowledgeProvider()
        items = [
            {"title": "Python Basics", "snippet": "Python is a high-level programming language."},
            {"title": "Python Uses", "snippet": "Python is used in web dev, data science, and AI."},
        ]
        with patch("app.services.ai_service.generate_text", return_value=self._mock_llm(items)):
            result = p.search("Python programming")
        assert len(result) == 2

    def test_source_type_is_ai_knowledge(self):
        p = AIKnowledgeProvider()
        items = [{"title": "Test", "snippet": "Some knowledge."}]
        with patch("app.services.ai_service.generate_text", return_value=self._mock_llm(items)):
            result = p.search("test")
        assert result[0].source_type == SourceType.ai_knowledge

    def test_credibility_score_is_0_5(self):
        p = AIKnowledgeProvider()
        items = [{"title": "Test", "snippet": "Some knowledge."}]
        with patch("app.services.ai_service.generate_text", return_value=self._mock_llm(items)):
            result = p.search("test")
        assert result[0].credibility_score == 0.5

    def test_url_is_empty_string(self):
        p = AIKnowledgeProvider()
        items = [{"title": "Test", "snippet": "Knowledge here."}]
        with patch("app.services.ai_service.generate_text", return_value=self._mock_llm(items)):
            result = p.search("test")
        assert result[0].url == ""

    def test_llm_error_returns_empty_list(self):
        p = AIKnowledgeProvider()
        with patch("app.services.ai_service.generate_text", side_effect=Exception("API error")):
            result = p.search("test")
        assert result == []

    def test_invalid_json_returns_empty_list(self):
        p = AIKnowledgeProvider()
        with patch("app.services.ai_service.generate_text", return_value="not valid json at all"):
            result = p.search("test")
        assert result == []

    def test_items_without_snippet_skipped(self):
        p = AIKnowledgeProvider()
        items = [{"title": "Test", "snippet": ""}, {"title": "Good", "snippet": "Has content."}]
        with patch("app.services.ai_service.generate_text", return_value=self._mock_llm(items)):
            result = p.search("test")
        assert len(result) == 1
        assert result[0].title == "Good"

    def test_max_results_respected(self):
        p = AIKnowledgeProvider()
        items = [{"title": f"Item {i}", "snippet": f"Content {i}."} for i in range(5)]
        with patch("app.services.ai_service.generate_text", return_value=self._mock_llm(items)):
            result = p.search("test", max_results=2)
        assert len(result) <= 2

    def test_markdown_fences_stripped(self):
        p = AIKnowledgeProvider()
        items = [{"title": "Test", "snippet": "Content."}]
        import json
        fenced = f"```json\n{json.dumps(items)}\n```"
        with patch("app.services.ai_service.generate_text", return_value=fenced):
            result = p.search("test")
        assert len(result) == 1
