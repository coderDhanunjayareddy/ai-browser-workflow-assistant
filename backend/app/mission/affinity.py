"""
V5.0 Mission Layer — Mission-Aware Task Assignment (Affinity Heuristic).

Determines whether a new task belongs to an existing active mission or
should start a new one. No LLM required — pure deterministic keyword matching.

Algorithm:
  1. Extract keywords from task.original_query (remove stop words, length >= 3)
  2. For each active mission, collect keyword union from all attached tasks
  3. Compute Jaccard similarity between task keywords and mission keywords
  4. If similarity >= AFFINITY_THRESHOLD → attach to that mission
  5. If multiple missions match → pick highest similarity
  6. If no match → create a new mission from the task query

Domain detection: Tasks in completely different domains are never matched.
  "book flight to NYC" vs "research best laptops" → different domains.
"""
from __future__ import annotations

import re
import logging
from typing import Optional

from app.mission.models import Mission
from app.unified.models import UnifiedTask

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

AFFINITY_THRESHOLD: float = 0.25

STOP_WORDS: set[str] = {
    "the", "a", "an", "to", "for", "of", "in", "on", "and", "or", "is",
    "it", "i", "my", "me", "we", "us", "be", "do", "did", "get", "got",
    "can", "will", "would", "could", "should", "want", "need", "that",
    "this", "with", "from", "at", "by", "as", "are", "was", "has", "have",
    "had", "not", "so", "if", "up", "but", "what", "how", "when", "which",
    "all", "any", "best", "most", "more", "some", "there",
}

# Mutually-exclusive domain clusters. Keywords in different clusters → no match.
_DOMAIN_CLUSTERS: list[set[str]] = [
    {"flight", "hotel", "trip", "travel", "vacation", "airport", "airline",
     "booking", "cruise", "train", "bus", "tickets", "visa", "passport"},
    {"laptop", "phone", "tablet", "computer", "gpu", "cpu", "ram", "ssd",
     "headphones", "monitor", "keyboard", "mouse", "electronics"},
    {"restaurant", "food", "eat", "dinner", "lunch", "breakfast", "cook",
     "recipe", "meal", "cafe", "cuisine", "menu"},
    {"movie", "music", "album", "concert", "show", "game", "video", "stream",
     "entertainment", "podcast", "book", "novel"},
    {"insurance", "mortgage", "loan", "bank", "invest", "stock", "finance",
     "credit", "tax", "salary", "budget"},
]


# ── Keyword extraction ────────────────────────────────────────────────────────

def _extract_keywords(text: str) -> set[str]:
    """Return lowercase, non-stop content words of length >= 3."""
    words = re.findall(r"[a-zA-Z]+", text.lower())
    return {w for w in words if len(w) >= 3 and w not in STOP_WORDS}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union)


def _domain_of(keywords: set[str]) -> Optional[int]:
    """Return the index of the domain cluster that contains any keyword, or None."""
    for i, cluster in enumerate(_DOMAIN_CLUSTERS):
        if keywords & cluster:
            return i
    return None


def _same_domain(kw_a: set[str], kw_b: set[str]) -> bool:
    """Return True if both keyword sets are in the same domain (or either is uncategorized)."""
    da = _domain_of(kw_a)
    db = _domain_of(kw_b)
    if da is None or db is None:
        return True  # one or both uncategorized → allow potential match
    return da == db


# ── Mission keyword cache (lazy, per-call) ────────────────────────────────────

def _mission_keywords(mission: Mission) -> set[str]:
    """Return the keyword union from all task queries attached to a mission."""
    from app.unified import store as task_store
    combined: set[str] = _extract_keywords(mission.title + " " + mission.objective)
    for tid in mission.task_ids:
        task = task_store.get(tid)
        if task:
            combined |= _extract_keywords(task.original_query)
    return combined


# ── Public API ────────────────────────────────────────────────────────────────

def find_matching_mission(task: UnifiedTask) -> Optional[Mission]:
    """
    Find the best-matching active mission for a task.
    Returns None if no active mission has affinity >= AFFINITY_THRESHOLD.
    """
    from app.mission import store as mission_store

    task_kw = _extract_keywords(task.original_query)
    if not task_kw:
        return None

    best_mission: Optional[Mission] = None
    best_score: float = 0.0

    for mission in mission_store.active_missions():
        if mission.is_terminal:
            continue
        mission_kw = _mission_keywords(mission)
        if not _same_domain(task_kw, mission_kw):
            continue
        score = _jaccard(task_kw, mission_kw)
        if score >= AFFINITY_THRESHOLD and score > best_score:
            best_score = score
            best_mission = mission

    if best_mission:
        logger.debug(
            "Affinity match: task %r → mission %s (score=%.2f)",
            task.original_query, best_mission.mission_id, best_score,
        )
    return best_mission


def assign_task_to_mission(task: UnifiedTask, create_if_none: bool = True) -> Optional[Mission]:
    """
    Auto-assign a task to the best matching active mission.

    If create_if_none=True and no mission matches, creates a new mission
    whose title/objective are derived from the task query.

    Returns the mission (existing or new) the task was assigned to,
    or None if create_if_none=False and no match was found.
    """
    from app.mission import lifecycle as mission_lifecycle

    match = find_matching_mission(task)
    if match is not None:
        mission_lifecycle.attach_task(match.mission_id, task.task_id)
        return match

    if not create_if_none:
        return None

    # Create a new mission from the task
    title = _derive_title(task.original_query)
    new_mission = mission_lifecycle.create_mission_obj(
        title=title,
        objective=task.original_query,
    )
    mission_lifecycle.attach_task(new_mission.mission_id, task.task_id)
    return new_mission


def _derive_title(query: str) -> str:
    """Derive a short mission title from a query string (≤ 60 chars)."""
    title = query.strip()
    if len(title) > 60:
        title = title[:57] + "..."
    return title or "New Mission"


def score_pair(query_a: str, query_b: str) -> float:
    """Return Jaccard similarity between two query strings (for testing/debugging)."""
    return _jaccard(_extract_keywords(query_a), _extract_keywords(query_b))
