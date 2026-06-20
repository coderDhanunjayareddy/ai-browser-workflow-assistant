from typing import Dict, Any

class RemedyDatabase:
    """
    Component 8.2: Remedy database
    Provides remediation descriptions for classified failure codes.
    """
    REMEDIES = {
        "SELECTOR_STALE": {
            "strategy": "recalculate_selectors",
            "action": "wait",
            "value": "3000",
            "description": "DOM layout shift detected. Waiting 3000ms and re-attempting locators ranking lookup."
        },
        "POPUP_BLOCKING": {
            "strategy": "dismiss_overlay",
            "action": "click",
            "selector": "body",  # Clicks outside to dismiss popup
            "description": "Popup modal blocking element. Click body area to dismiss overlay."
        },
        "RESULTS_NOT_LOADED": {
            "strategy": "page_refresh",
            "action": "wait",
            "value": "5000",
            "description": "Network delay detected. Wait 5000ms and check search result grids again."
        },
        "VALIDATION_MISMATCH_ORIGIN_VALUE_NOT_SELECTED": {
            "strategy": "reopen_origin_picker",
            "action": "click",
            "selector": "#fromCity",
            "description": "Origin city was not verified. Reopen the From city picker."
        },
        "VALIDATION_MISMATCH_ORIGIN_NOT_SELECTED": {
            "strategy": "reopen_origin_picker",
            "action": "click",
            "selector": "#fromCity",
            "description": "Origin city is missing. Open the From city picker."
        },
        "VALIDATION_MISMATCH_DESTINATION_VALUE_NOT_SELECTED": {
            "strategy": "reopen_destination_picker",
            "action": "click",
            "selector": "#toCity",
            "description": "Destination city was not verified. Reopen the To city picker."
        },
        "VALIDATION_MISMATCH_DESTINATION_NOT_SELECTED": {
            "strategy": "reopen_destination_picker",
            "action": "click",
            "selector": "#toCity",
            "description": "Destination city is missing. Open the To city picker."
        },
        "VALIDATION_MISMATCH_DATE_NOT_SELECTED": {
            "strategy": "reopen_date_picker",
            "action": "click",
            "selector": "[data-cy='departureDate']",
            "description": "Departure date is not verified. Open the date picker."
        },
        "VALIDATION_MISMATCH_SEARCH_NOT_CLICKED": {
            "strategy": "retry_search",
            "action": "click",
            "selector": "a.primaryBtn",
            "description": "Search was not verified. Retry the visible flight search button."
        },
        "VALIDATION_MISMATCH_FLIGHTS_LIST_NOT_LOADED": {
            "strategy": "wait_for_flight_results",
            "action": "wait",
            "value": "5000",
            "description": "Flight results are not visible yet. Wait for result cards to load."
        },
    }

    @classmethod
    def get_remedy(cls, error_code: str) -> Dict[str, Any]:
        return cls.REMEDIES.get(error_code, {
            "strategy": "generic_retry",
            "action": "wait",
            "value": "2000",
            "description": "Generic failure recovery: waiting 2000ms and retrying action."
        })
