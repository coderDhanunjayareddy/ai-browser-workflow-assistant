"""
V7.5 Decision Center — DecisionAggregator.

Collects DecisionItems from all source adapters for a mission,
stores them in the DecisionRegistry, and records analytics + timeline events.

Sources (in order):
  1. trust_engine      (V6.5 TrustEvaluation)
  2. mission_intelligence (V5.5 MissionIntelligenceReport)
  3. browser_sync      (V7.0 RecommendationRefreshEngine)
  4. research_layer    (V3.5 MissionMemory)

Does NOT duplicate any source logic.
"""
from __future__ import annotations

import time
from typing import Optional

from app.decisions import registry as reg
from app.decisions import analytics as anal
from app.decisions import timeline  as tl
from app.decisions.models import DecisionItem


class DecisionAggregator:

    def aggregate(self, mission_id: str) -> list[DecisionItem]:
        """
        Pull items from all source adapters, store new ones in the registry,
        and return the full list for this mission (new + existing).
        """
        new_items: list[DecisionItem] = []

        # 1. Trust source
        try:
            from app.decisions.sources import trust as trust_src
            new_items.extend(trust_src.decisions_for_mission(mission_id))
        except Exception:
            pass

        # 2. Mission intelligence source
        try:
            from app.decisions.sources import mission as mission_src
            new_items.extend(mission_src.decisions_for_mission(mission_id))
        except Exception:
            pass

        # 3. Browser recommendations source
        try:
            from app.decisions.sources import browser as browser_src
            new_items.extend(browser_src.decisions_for_mission(mission_id))
        except Exception:
            pass

        # 4. Research source
        try:
            from app.decisions.sources import research as research_src
            new_items.extend(research_src.decisions_for_mission(mission_id))
        except Exception:
            pass

        # Store new items
        for item in new_items:
            reg.add(item)
            anal.record_created(item.priority.value)
            tl.record(
                item.decision_id,
                "created",
                mission_id = mission_id,
                priority   = item.priority.value,
                title      = item.title,
                source     = item.source,
            )

        # Return all items for this mission
        return reg.list_for_mission(mission_id)


# Module-level singleton
_aggregator = DecisionAggregator()


def aggregate(mission_id: str) -> list[DecisionItem]:
    return _aggregator.aggregate(mission_id)
