import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class LocatorRegistry:
    """
    Component 7: Locator Registry
    Tracks historical locator success and failure counts per site domain.
    """
    def __init__(self):
        # Maps domain -> selector -> {"success": int, "fail": int}
        self.stats: Dict[str, Dict[str, Dict[str, int]]] = {}

    def record_success(self, domain: str, selector: str) -> None:
        domain_stats = self.stats.setdefault(domain, {})
        selector_stats = domain_stats.setdefault(selector, {"success": 0, "fail": 0})
        selector_stats["success"] += 1
        logger.info(f"Recorded selector success for {domain}: {selector} (successes={selector_stats['success']})")

    def record_failure(self, domain: str, selector: str) -> None:
        domain_stats = self.stats.setdefault(domain, {})
        selector_stats = domain_stats.setdefault(selector, {"success": 0, "fail": 0})
        selector_stats["fail"] += 1
        logger.warning(f"Recorded selector failure for {domain}: {selector} (failures={selector_stats['fail']})")

    def get_selector_rank(self, domain: str, selector: str) -> float:
        """
        Returns a ratio representing locator reliability. Defaults to 1.0.
        """
        domain_stats = self.stats.get(domain, {})
        selector_stats = domain_stats.get(selector)
        if not selector_stats:
            return 1.0
            
        successes = selector_stats["success"]
        failures = selector_stats["fail"]
        total = successes + failures
        if total == 0:
            return 1.0
            
        return successes / total
