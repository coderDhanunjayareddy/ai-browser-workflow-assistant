import pytest

from app.context_compression.state_summarizer import StateSummarizer
from app.runtime_state_manager.execution_result import is_successful_execution_result


@pytest.mark.parametrize("result, expected", [
    ("CDP click dispatched via stable_selector grounding.\n\nExecution: success\nVerification: verified", True),
    ("CDP fill dispatched\nVerification: verified", True),
    ("CDP click dispatched", False),
    ("Clicked target\nVerification: no_effect", False),
    ("success\nExecution: failed\nVerification: verified", False),
    ("success\nVerification: execution_failed", False),
    ("success", True),
    ("Navigating to: https://example.test/", True),
])
def test_execution_result_uses_verified_outcome_before_adapter_wording(result, expected):
    assert is_successful_execution_result(result) is expected


def test_verified_cdp_menu_click_reaches_planner_progress():
    result = StateSummarizer().summarize(
        active_goal="Open menu then select Workspace", verified_facts={},
        prior_steps=[{
            "action_type": "click", "target_selector": "#menu", "description": "Open menu",
            "execution_result": "CDP click dispatched via stable_selector grounding.\nVerification: verified",
        }],
    )
    assert result["completed_nodes"][0]["selector"] == "#menu"
    assert result["important_failures"] == []
