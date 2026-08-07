import json

from app.services.ai_service import budget_compressed_planner_context


def test_budget_compressed_planner_context_preserves_high_value_search_results():
    context = {
        "active_goal": "compare browser automation tools",
        "verified_facts": {
            "relevant_visible_content": [
                {"selector": "#x", "text": "A" * 5000},
            ],
        },
        "relevant_elements": [
            {"selector": f"#r{i}", "text": "Result " + ("x" * 400)}
            for i in range(60)
        ],
        "browser_intelligence": {
            "search_results": [
                {"rank": i, "title": f"Tool {i}", "url": f"https://example.com/{i}"}
                for i in range(20)
            ],
            "semantic_elements": [
                {"label": "Element " + ("x" * 600), "selector_id": f"s{i}"}
                for i in range(40)
            ],
            "semantic_entities": [
                {"title": "Entity " + ("x" * 600), "canonical_url": f"https://entity.test/{i}"}
                for i in range(40)
            ],
        },
        "recent_actions": [
            {"description": "Clicked result " + ("x" * 500), "execution_result": "success"}
            for _ in range(20)
        ],
    }

    projected = budget_compressed_planner_context(context, char_budget=6000)

    assert len(json.dumps(projected, ensure_ascii=False)) <= 6000
    assert projected["active_goal"] == context["active_goal"]
    assert projected["browser_intelligence"]["search_results"]
    assert projected["browser_intelligence"]["search_results"][0]["url"] == "https://example.com/0"


def test_default_budget_keeps_context_under_provider_prompt_headroom():
    context = {
        "active_goal": "compare browser automation tools",
        "verified_facts": {"visible_text": "A" * 10_000},
        "browser_intelligence": {
            "search_results": [
                {
                    "rank": i,
                    "title": f"Tool {i} " + ("x" * 500),
                    "url": f"https://example.com/{i}",
                    "description": "d" * 1000,
                }
                for i in range(20)
            ],
            "semantic_elements": [{"label": "Element " + ("x" * 800)} for _ in range(40)],
            "semantic_entities": [{"title": "Entity " + ("x" * 800)} for _ in range(40)],
        },
        "recent_actions": [
            {"description": "Action " + ("x" * 800), "execution_result": "success " + ("y" * 800)}
            for _ in range(20)
        ],
    }

    projected = budget_compressed_planner_context(context)

    assert len(json.dumps(projected, ensure_ascii=False)) <= 5500
    assert projected["browser_intelligence"]["search_results"]
