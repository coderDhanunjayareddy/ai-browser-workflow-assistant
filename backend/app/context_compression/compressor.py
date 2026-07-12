from typing import Any

from app.context_compression.relevance_ranker import RelevanceRanker
from app.context_compression.state_summarizer import StateSummarizer

_MAX_RELEVANT_CONTENT_BLOCKS = 3
_MAX_RELEVANT_CONTENT_CHARS = 500


def _as_dict(item: Any) -> dict:
    if hasattr(item, "model_dump"):
        return item.model_dump()
    if isinstance(item, dict):
        return dict(item)
    return {}


def _terms(text: str) -> set[str]:
    return RelevanceRanker._terms(text)


def _snippet(text: str) -> str:
    return " ".join(str(text or "").split())[:_MAX_RELEVANT_CONTENT_CHARS]


def _relevant_visible_content(task: str, page_context: Any) -> list[dict[str, str]]:
    task_terms = _terms(task)
    if not task_terms:
        return []

    candidates: list[tuple[int, int, dict[str, str]]] = []
    for index, block in enumerate(getattr(page_context, "content_blocks", []) or []):
        data = _as_dict(block)
        text = _snippet(data.get("text", ""))
        if not text:
            continue
        overlap = len(task_terms & _terms(text))
        if overlap:
            candidates.append((
                overlap,
                -index,
                {"selector": str(data.get("selector") or ""), "text": text},
            ))

    if not candidates:
        lines = [
            _snippet(line)
            for line in str(getattr(page_context, "visible_text", "") or "").splitlines()
        ]
        relevant_lines = [
            line for line in lines if line and task_terms & _terms(line)
        ][:_MAX_RELEVANT_CONTENT_BLOCKS]
        return [
            {"selector": "visible_text", "text": line}
            for line in relevant_lines
        ]

    candidates.sort(reverse=True, key=lambda row: (row[0], row[1]))
    return [entry for *_, entry in candidates[:_MAX_RELEVANT_CONTENT_BLOCKS]]


def _with_relevant_visible_content(
    verified_facts: dict[str, Any],
    task: str,
    page_context: Any,
) -> dict[str, Any]:
    content = _relevant_visible_content(task, page_context)
    if not content:
        return verified_facts

    enriched = dict(verified_facts)
    enriched.setdefault("relevant_visible_content", content)
    return enriched


class ContextCompressor:
    """Produces the only context shape accepted by the interactive planner."""

    def __init__(self, element_limit: int = 30):
        self.ranker = RelevanceRanker(element_limit)
        self.summarizer = StateSummarizer()

    def compress(
        self,
        *,
        task: str,
        page_context: Any,
        verified_facts: dict,
        prior_steps: list,
        task_constraints: list[str] | None = None,
        cognitive_context: dict | None = None,
    ) -> dict:
        state = self.summarizer.summarize(
            active_goal=task, verified_facts=verified_facts, prior_steps=prior_steps
        )
        result = {
            "verified_facts": _with_relevant_visible_content(
                state["verified_facts"], task, page_context
            ),
            "active_goal": state["active_goal"],
            "relevant_elements": self.ranker.rank(task, page_context.interactive_elements),
            # M1.1: episodic memory — previously-successful actions (with selector) that were
            # computed by StateSummarizer but discarded before this point. Restoring this is
            # the entire M1.1 change; see docs/m1-engineering-spec.md Part 4.1.
            "recent_actions": state["completed_nodes"],
            "important_failures": state["important_failures"],
            "task_constraints": task_constraints or [],
        }
        # V3.0: inject cognitive context when available (7th key, optional)
        if cognitive_context:
            result["cognitive_context"] = cognitive_context
        return result
