from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.budget_engine.budget_models import WorkflowBudget
from app.context_compression.compressor import ContextCompressor
from app.domain_models import ProductCard
from app.exploration import ExplorationPlanner
from app.schemas.request import InteractiveElement, PageContext, PriorStep


def page(elements):
    return PageContext(
        url="https://example.com", title="Example", interactive_elements=elements,
        content_blocks=[], headings=[], selected_text="", visible_text="full text must not leak",
        images=[],
    )


def test_budget_detects_each_hard_limit():
    assert WorkflowBudget(steps_used=50).exhausted_reason()
    assert WorkflowBudget(tokens_used=50_000).exhausted_reason()
    assert WorkflowBudget(retries_used=5).exhausted_reason()
    old = datetime.now(timezone.utc) - timedelta(seconds=301)
    assert WorkflowBudget(started_at=old).exhausted_reason()


def test_compressor_emits_only_planner_contract_and_ranks_relevance():
    elements = [
        InteractiveElement(type="button", text="Help", selector="#help", visible=True),
        InteractiveElement(type="button", text="Search flights", selector="#search", visible=True),
    ]
    result = ContextCompressor(element_limit=1).compress(
        task="search flights", page_context=page(elements), verified_facts={"origin": "HYD"},
        prior_steps=[PriorStep(action_type="fill", description="Set origin", execution_result="success")],
    )
    assert set(result) == {"verified_facts", "active_goal", "relevant_elements", "important_failures", "task_constraints"}
    assert result["relevant_elements"][0]["selector"] == "#search"
    assert "full text must not leak" not in str(result)


def test_typed_domain_output_rejects_invalid_data():
    with pytest.raises(ValidationError):
        ProductCard(title="Bad", price=-1, rating=9, url="not-a-url")


def test_exploration_is_bounded_and_grounded():
    selected = ExplorationPlanner().explore(
        {"action_type": "click", "description": "Search flights", "target_selector": "#stale"},
        [
            {"text": "Search flights", "selector": "#fresh"},
            {"text": "Cancel", "selector": "#cancel"},
        ],
    )
    assert selected and selected["target_selector"] == "#fresh"
