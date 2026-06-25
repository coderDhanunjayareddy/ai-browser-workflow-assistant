"""
ResearchPlanner: deterministic 4-stage research plan from a user query.

No LLM call here. Topic and queries are derived by simple text heuristics
to keep the plan fast, reproducible, and testable.
"""
from __future__ import annotations

import re

from app.research.models import ResearchPlan

_STAGES = [
    "Define topic",
    "Gather evidence",
    "Analyze evidence",
    "Produce findings",
]

_FILLER = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "of", "in",
    "to", "and", "or", "for", "on", "at", "by", "with", "from",
    "about", "what", "who", "when", "where", "why", "how", "me",
    "i", "my", "can", "do", "does", "tell",
})

_RESEARCH_PREFIXES = (
    "research ", "find info about ", "find information about ",
    "look up ", "look into ", "investigate ",
)


def extract_topic(message: str) -> str:
    """Strip leading research verb phrases and return the bare topic string."""
    lowered = message.lower().strip()
    for prefix in _RESEARCH_PREFIXES:
        if lowered.startswith(prefix):
            return message[len(prefix):].strip()
    return message.strip()


def _keywords(topic: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9]+", topic)
    return [w for w in words if w.lower() not in _FILLER and len(w) > 2]


def create_plan(message: str) -> ResearchPlan:
    """
    Build a deterministic ResearchPlan from a user query.

    Generates 3 queries:
      1. The raw topic (exact match)
      2. "{topic} explained" (contextual overview)
      3. "{top keywords}" (keyword-focused search)
    """
    topic = extract_topic(message)
    kws = _keywords(topic)
    kw_query = " ".join(kws[:4]) if kws else topic

    queries: list[str] = []
    queries.append(topic)
    if kw_query.lower() != topic.lower():
        queries.append(kw_query)
    queries.append(f"{topic} overview")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique: list[str] = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            unique.append(q)

    return ResearchPlan(topic=topic, queries=unique, stages=list(_STAGES))
