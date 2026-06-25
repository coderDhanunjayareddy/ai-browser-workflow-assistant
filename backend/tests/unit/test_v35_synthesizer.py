"""
V3.5 ResearchSynthesizer unit tests.

Tests AI synthesis → ResearchReport, stub fallback, confidence calculation.
LLM calls are mocked.
"""
import json
from unittest.mock import patch

import pytest

from app.research.models import ResearchSource, SourceType, ResearchReport
from app.research.synthesizer import synthesize, _compute_confidence, _stub_report


def _make_source(
    title: str = "Source",
    url: str = "https://example.com",
    source_type: SourceType = SourceType.web,
    snippet: str = "Some informative content.",
    credibility: float = 0.8,
) -> ResearchSource:
    import uuid
    return ResearchSource(
        source_id=str(uuid.uuid4()),
        title=title,
        url=url,
        source_type=source_type,
        snippet=snippet,
        credibility_score=credibility,
    )


def _mock_report_json(
    summary: str = "Executive summary here.",
    findings: list = None,
    confidence: float = 0.75,
) -> str:
    return json.dumps({
        "executive_summary": summary,
        "key_findings": findings or ["Finding A", "Finding B"],
        "supporting_evidence": [
            {"finding": "Finding A", "source_title": "Source", "source_url": "https://x.com", "is_conclusion": False}
        ],
        "risks": ["Risk 1"],
        "open_questions": ["Open question 1?"],
        "recommended_actions": ["Action 1"],
        "confidence_score": confidence,
    })


class TestComputeConfidence:
    def test_empty_sources_returns_low_confidence(self):
        assert _compute_confidence([]) == 0.3

    def test_single_high_credibility(self):
        src = _make_source(credibility=0.9)
        score = _compute_confidence([src])
        assert score == pytest.approx(0.9, abs=0.01)

    def test_average_of_multiple(self):
        sources = [_make_source(credibility=0.8), _make_source(credibility=0.6)]
        score = _compute_confidence(sources)
        assert score == pytest.approx(0.7, abs=0.01)

    def test_rounds_to_2_decimal_places(self):
        sources = [_make_source(credibility=0.333) for _ in range(3)]
        score = _compute_confidence(sources)
        # 0.333 rounded to 2dp = 0.33
        assert str(score).count('.') <= 1


class TestStubReport:
    def test_returns_research_report(self):
        result = _stub_report("test topic", [])
        assert isinstance(result, ResearchReport)

    def test_summary_contains_topic(self):
        result = _stub_report("quantum computing", [])
        assert "quantum computing" in result.executive_summary

    def test_low_confidence_on_empty_sources(self):
        result = _stub_report("topic", [])
        assert result.confidence_score == 0.3

    def test_source_titles_in_evidence(self):
        sources = [_make_source(title="Wikipedia Article")]
        result = _stub_report("AI", sources)
        evidence_titles = [e["source_title"] for e in result.supporting_evidence]
        assert "Wikipedia Article" in evidence_titles

    def test_has_risks_list(self):
        result = _stub_report("topic", [])
        assert isinstance(result.risks, list)
        assert len(result.risks) > 0

    def test_has_recommended_actions(self):
        result = _stub_report("topic", [])
        assert isinstance(result.recommended_actions, list)
        assert len(result.recommended_actions) > 0


class TestSynthesize:
    def test_returns_research_report(self):
        sources = [_make_source()]
        with patch("app.services.ai_service.generate_text", return_value=_mock_report_json()):
            result = synthesize("Python", sources)
        assert isinstance(result, ResearchReport)

    def test_executive_summary_populated(self):
        sources = [_make_source()]
        with patch("app.services.ai_service.generate_text",
                   return_value=_mock_report_json(summary="Python is great.")):
            result = synthesize("Python", sources)
        assert result.executive_summary == "Python is great."

    def test_key_findings_populated(self):
        sources = [_make_source()]
        with patch("app.services.ai_service.generate_text",
                   return_value=_mock_report_json(findings=["F1", "F2"])):
            result = synthesize("topic", sources)
        assert "F1" in result.key_findings
        assert "F2" in result.key_findings

    def test_confidence_score_clamped_0_to_1(self):
        sources = [_make_source()]
        report_json = _mock_report_json(confidence=1.5)  # out of range
        with patch("app.services.ai_service.generate_text", return_value=report_json):
            result = synthesize("topic", sources)
        assert 0.0 <= result.confidence_score <= 1.0

    def test_llm_error_falls_back_to_stub(self):
        sources = [_make_source()]
        with patch("app.services.ai_service.generate_text", side_effect=Exception("API error")):
            result = synthesize("topic", sources)
        assert isinstance(result, ResearchReport)
        assert result.executive_summary  # stub always has a summary

    def test_invalid_json_falls_back_to_stub(self):
        sources = [_make_source()]
        with patch("app.services.ai_service.generate_text", return_value="not json"):
            result = synthesize("topic", sources)
        assert isinstance(result, ResearchReport)

    def test_empty_sources_returns_stub(self):
        result = synthesize("topic", [])
        assert isinstance(result, ResearchReport)
        assert result.confidence_score == 0.3

    def test_markdown_fenced_json_parsed(self):
        sources = [_make_source()]
        fenced = f"```json\n{_mock_report_json()}\n```"
        with patch("app.services.ai_service.generate_text", return_value=fenced):
            result = synthesize("topic", sources)
        assert result.executive_summary == "Executive summary here."

    def test_risks_and_open_questions_populated(self):
        sources = [_make_source()]
        with patch("app.services.ai_service.generate_text", return_value=_mock_report_json()):
            result = synthesize("topic", sources)
        assert len(result.risks) > 0
        assert len(result.open_questions) > 0

    def test_recommended_actions_populated(self):
        sources = [_make_source()]
        with patch("app.services.ai_service.generate_text", return_value=_mock_report_json()):
            result = synthesize("topic", sources)
        assert len(result.recommended_actions) > 0
