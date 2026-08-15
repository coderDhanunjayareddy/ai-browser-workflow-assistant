from benchmark.analyze_client import parse_analyze_response


def test_completed_non_browser_intent_is_exposed_as_backend_progress() -> None:
    result = parse_analyze_response({
        "analysis": "Collected search results deterministically.",
        "outcome_kind": "act",
        "suggested_actions": [],
        "intent_dispatch": {
            "intent": "collect_search_results",
            "reason": "Collect current SERP entities.",
        },
        "intent_execution": {
            "status": "succeeded",
            "reason": "Collected 5 observed search results.",
            "browser_action": None,
        },
    })

    assert result.backend_progress is True
    assert result.backend_action_type == "collect_search_results"
    assert result.backend_progress_detail == "Collected 5 observed search results."


def test_empty_response_without_execution_receipt_is_not_progress() -> None:
    result = parse_analyze_response({
        "analysis": "No action.",
        "outcome_kind": "act",
        "suggested_actions": [],
    })

    assert result.backend_progress is False
