import pytest
from app.locator_engine.locator_ranker import LocatorRanker
from app.locator_engine.locator_score import LocatorScorer

def test_locator_scorer_penalties():
    # Regular css selector with no digits
    score1 = LocatorScorer.calculate_score("css_selector", {"locator": "button.search-btn"})
    # css selector with digit
    score2 = LocatorScorer.calculate_score("css_selector", {"locator": "button.search-btn-123"})
    
    assert score2 < score1

def test_locator_ranker_ordering():
    meta = {
        "accessibility_name": "Search Flight",
        "aria_label": "MMT search flights",
        "data_testid": "search-submit",
        "text": "Search",
        "selector": "button.search"
    }
    ranked = LocatorRanker.rank_locators(meta)
    
    assert len(ranked) >= 4
    # The first one should be accessibility_name (95 score)
    assert ranked[0]["type"] == "accessibility_name"
    # Second should be aria_label (92 score)
    assert ranked[1]["type"] == "aria_label"
