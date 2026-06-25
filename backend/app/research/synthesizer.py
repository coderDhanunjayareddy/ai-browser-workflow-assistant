"""
ResearchSynthesizer: LLM-based synthesis of collected sources into a ResearchReport.

Uses the configured AI provider (generate_text) to produce structured JSON.
The prompt is strict: model must output a JSON object matching ResearchReport's fields.
"""
from __future__ import annotations

import json
import re
import logging

from app.research.models import ResearchSource, ResearchReport

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a research synthesis assistant. "
    "Read the provided sources and produce a structured research report. "
    "Output ONLY a valid JSON object — no prose, no markdown fences."
)

_REPORT_SCHEMA = """
{
  "executive_summary": "<2-4 sentence high-level overview>",
  "key_findings": ["<finding 1>", "<finding 2>", ...],
  "supporting_evidence": [
    {
      "finding": "<which finding this supports>",
      "source_title": "<title>",
      "source_url": "<url or empty string>",
      "is_conclusion": false
    }
  ],
  "risks": ["<risk or caveat 1>", ...],
  "open_questions": ["<question 1>", ...],
  "recommended_actions": ["<action 1>", ...],
  "confidence_score": 0.75
}
"""


def _build_sources_text(sources: list[ResearchSource]) -> str:
    parts = []
    for i, s in enumerate(sources, 1):
        line = (
            f"[Source {i}] {s.title} (credibility={s.credibility_score:.1f})\n"
            f"URL: {s.url or 'N/A'}\n"
            f"Type: {s.source_type.value}\n"
            f"Snippet: {s.snippet}\n"
        )
        parts.append(line)
    return "\n".join(parts)


def _build_prompt(topic: str, sources: list[ResearchSource]) -> str:
    sources_text = _build_sources_text(sources)
    return (
        f"Research Topic: {topic}\n\n"
        f"SOURCES:\n{sources_text}\n\n"
        f"Produce a research report in this exact JSON format:\n{_REPORT_SCHEMA}\n\n"
        f"Rules:\n"
        f"- key_findings: 3-5 bullet points\n"
        f"- supporting_evidence: one entry per key finding, citing the most relevant source\n"
        f"- risks: flag low-credibility sources or gaps in evidence\n"
        f"- open_questions: note anything the sources don't resolve\n"
        f"- recommended_actions: concrete next steps the user should take\n"
        f"- confidence_score: average weighted credibility of sources (0.0-1.0)\n"
        f"Output ONLY the JSON object."
    )


def _parse_report(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object in synthesis response")
    candidate = text[start:end + 1]
    # Remove trailing commas before } and ]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    return json.loads(candidate)


def _compute_confidence(sources: list[ResearchSource]) -> float:
    if not sources:
        return 0.3
    return round(sum(s.credibility_score for s in sources) / len(sources), 2)


def synthesize(topic: str, sources: list[ResearchSource]) -> ResearchReport:
    """
    Call the AI provider to synthesize sources into a ResearchReport.
    Falls back to a minimal stub report if synthesis fails.
    """
    if not sources:
        return _stub_report(topic, sources)

    try:
        from app.services.ai_service import generate_text
        prompt = _build_prompt(topic, sources)
        raw = generate_text(_SYSTEM, prompt)
        data = _parse_report(raw)
    except Exception as exc:
        logger.warning("Research synthesis failed for %r: %s", topic, exc)
        return _stub_report(topic, sources)

    confidence = float(data.get("confidence_score") or _compute_confidence(sources))
    confidence = max(0.0, min(1.0, confidence))

    return ResearchReport(
        executive_summary=str(data.get("executive_summary") or "").strip(),
        key_findings=[str(f) for f in (data.get("key_findings") or [])],
        supporting_evidence=data.get("supporting_evidence") or [],
        risks=[str(r) for r in (data.get("risks") or [])],
        open_questions=[str(q) for q in (data.get("open_questions") or [])],
        recommended_actions=[str(a) for a in (data.get("recommended_actions") or [])],
        confidence_score=confidence,
    )


def _stub_report(topic: str, sources: list[ResearchSource]) -> ResearchReport:
    """Minimal report returned when synthesis fails or no sources are found."""
    source_titles = [s.title for s in sources[:3]]
    return ResearchReport(
        executive_summary=(
            f"Research on '{topic}' completed with {len(sources)} source(s). "
            "Synthesis could not be completed — review sources directly."
        ),
        key_findings=[f"Found {len(sources)} source(s) for: {topic}"],
        supporting_evidence=[
            {"finding": f"Source: {t}", "source_title": t, "source_url": "", "is_conclusion": False}
            for t in source_titles
        ],
        risks=["Synthesis failed or no sources available — results may be incomplete."],
        open_questions=[f"Full research on '{topic}' pending."],
        recommended_actions=["Review sources manually", "Refine query and retry"],
        confidence_score=_compute_confidence(sources),
    )
