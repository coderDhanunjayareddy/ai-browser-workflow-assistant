from app.execution_orchestrator.artifact_registry import build_artifacts
from app.execution_orchestrator.budgets import build_budgets
from app.schemas.request import PageContext, PriorStep


def _page() -> PageContext:
    return PageContext(
        url="https://tool.example/",
        title="Tool",
        metadata={},
        interactive_elements=[],
        content_blocks=[],
        headings=[],
        selected_text="",
        visible_text="",
        images=[],
    )


def test_successful_repeated_waits_do_not_exhaust_retry_budget():
    steps = [
        PriorStep(
            action_type="wait",
            description="Wait for page",
            target_selector="window",
            value="1000",
            execution_result="success",
            page_url="https://tool.example/",
            page_title="Tool",
        )
        for _ in range(5)
    ]

    budgets = build_budgets(steps, build_artifacts(_page(), steps))

    assert budgets.consumed["retries"] == 0
    assert "max_retries" not in budgets.exhausted


def test_repeated_no_progress_attempts_exhaust_retry_budget():
    steps = [
        PriorStep(
            action_type="focus_existing_tab",
            description="Focus source",
            target_selector="",
            value="url:https://tool.example/",
            execution_result="Action reported success, but the page did not visibly change after focus_existing_tab. Retrying from the current page state.",
            page_url="https://tool.example/",
            page_title="Tool",
        )
        for _ in range(3)
    ]

    budgets = build_budgets(steps, build_artifacts(_page(), steps))

    assert budgets.consumed["retries"] == 3
    assert "max_retries" in budgets.exhausted
