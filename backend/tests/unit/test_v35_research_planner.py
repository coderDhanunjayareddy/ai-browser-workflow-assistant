"""
V3.5 Research Planner unit tests.

Tests deterministic plan creation: topic extraction, query generation, stage list.
No LLM calls — planner is pure-text heuristic.
"""
import pytest

from app.research.planner import extract_topic, create_plan, _keywords
from app.research.models import ResearchPlan


class TestExtractTopic:
    def test_strips_research_prefix(self):
        assert extract_topic("research quantum computing") == "quantum computing"

    def test_strips_look_up_prefix(self):
        assert extract_topic("look up flight prices") == "flight prices"

    def test_strips_find_info_about(self):
        assert extract_topic("find info about Tesla") == "Tesla"

    def test_strips_investigate(self):
        assert extract_topic("investigate climate change") == "climate change"

    def test_no_prefix_returns_original(self):
        assert extract_topic("quantum computing") == "quantum computing"

    def test_strips_find_information_about(self):
        assert extract_topic("find information about TypeScript") == "TypeScript"

    def test_look_into_prefix(self):
        assert extract_topic("look into blockchain technology") == "blockchain technology"

    def test_preserves_case(self):
        assert extract_topic("research FastAPI framework") == "FastAPI framework"

    def test_empty_string_returns_empty(self):
        assert extract_topic("") == ""


class TestKeywords:
    def test_filters_filler_words(self):
        kws = _keywords("what is the best framework")
        assert "what" not in kws
        assert "is" not in kws
        assert "the" not in kws

    def test_keeps_meaningful_words(self):
        kws = _keywords("best Python framework")
        assert "best" in kws
        assert "Python" in kws
        assert "framework" in kws

    def test_empty_topic(self):
        assert _keywords("") == []

    def test_short_words_filtered(self):
        kws = _keywords("AI in web")
        assert "in" not in kws


class TestCreatePlan:
    def test_returns_research_plan(self):
        plan = create_plan("research quantum computing")
        assert isinstance(plan, ResearchPlan)

    def test_topic_extracted(self):
        plan = create_plan("research quantum computing")
        assert plan.topic == "quantum computing"

    def test_queries_non_empty(self):
        plan = create_plan("look up climate change")
        assert len(plan.queries) >= 1

    def test_first_query_is_topic(self):
        plan = create_plan("research electric vehicles")
        assert plan.queries[0] == "electric vehicles"

    def test_has_overview_query(self):
        plan = create_plan("research machine learning")
        assert any("overview" in q for q in plan.queries)

    def test_four_stages(self):
        plan = create_plan("research AI")
        assert len(plan.stages) == 4

    def test_stage_names(self):
        plan = create_plan("research AI")
        assert plan.stages[0] == "Define topic"
        assert plan.stages[-1] == "Produce findings"

    def test_queries_no_duplicates(self):
        plan = create_plan("research AI")
        assert len(plan.queries) == len(set(plan.queries))

    def test_bare_message_without_prefix(self):
        plan = create_plan("Tesla electric cars")
        assert plan.topic == "Tesla electric cars"
        assert len(plan.queries) >= 1

    def test_keyword_query_excludes_stopwords(self):
        plan = create_plan("what is the best Python framework")
        kw_queries = [q for q in plan.queries if q != plan.topic and "overview" not in q]
        if kw_queries:
            assert "what" not in kw_queries[0]
            assert "the" not in kw_queries[0]
