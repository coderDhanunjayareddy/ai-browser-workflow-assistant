from typing import Any

from app.context_compression.relevance_ranker import RelevanceRanker
from app.context_compression.state_summarizer import StateSummarizer


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
            "verified_facts": state["verified_facts"],
            "active_goal": state["active_goal"],
            "relevant_elements": self.ranker.rank(task, page_context.interactive_elements),
            "important_failures": state["important_failures"],
            "task_constraints": task_constraints or [],
        }
        # V3.0: inject cognitive context when available (6th key, optional)
        if cognitive_context:
            result["cognitive_context"] = cognitive_context
        return result
