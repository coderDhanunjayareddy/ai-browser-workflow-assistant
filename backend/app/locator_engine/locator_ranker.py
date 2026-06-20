import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class LocatorRanker:
    """
    Component 7: Locator Ranking Engine
    Scores and orders locator candidates based on target reliability order.
    """
    SCORES = {
        "accessibility_name": 95,
        "aria_label": 92,
        "data_attribute": 90,
        "text_match": 84,
        "grounded_id": 80,
        "css_selector": 52,
        "xpath": 28
    }

    @classmethod
    def rank_locators(cls, element_meta: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Receives metadata for a target element and constructs ranked locator choices.
        """
        candidates = []
        
        # 1. Accessibility Name (OS accessibility tree tag name)
        if element_meta.get("accessibility_name"):
            candidates.append({
                "type": "accessibility_name",
                "locator": element_meta["accessibility_name"],
                "score": cls.SCORES["accessibility_name"]
            })

        # 2. ARIA label matches
        if element_meta.get("aria_label"):
            candidates.append({
                "type": "aria_label",
                "locator": f"[aria-label='{element_meta['aria_label']}']",
                "score": cls.SCORES["aria_label"]
            })

        # 3. Test IDs / custom data attributes
        if element_meta.get("data_testid"):
            candidates.append({
                "type": "data_attribute",
                "locator": f"[data-testid='{element_meta['data_testid']}']",
                "score": cls.SCORES["data_attribute"]
            })

        # 4. Text match fallback
        if element_meta.get("text"):
            clean_text = element_meta["text"].strip()
            if clean_text:
                candidates.append({
                    "type": "text_match",
                    "locator": f"text={clean_text}",
                    "score": cls.SCORES["text_match"]
                })

        # 5. Stable ground mappings
        if element_meta.get("grounded_id"):
            candidates.append({
                "type": "grounded_id",
                "locator": element_meta["grounded_id"],
                "score": cls.SCORES["grounded_id"]
            })

        # 6. Legacy CSS selector
        if element_meta.get("selector"):
            candidates.append({
                "type": "css_selector",
                "locator": element_meta["selector"],
                "score": cls.SCORES["css_selector"]
            })

        # Sort desc by score
        candidates.sort(key=lambda x: x["score"], reverse=True)
        logger.info(f"Generated {len(candidates)} ranked locators: {candidates}")
        return candidates
