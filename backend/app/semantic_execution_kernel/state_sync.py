from __future__ import annotations

from app.semantic_execution_kernel.models import BrowserContext, MissionState, SemanticEntity


def synchronization_summary(
    *,
    mission_state: MissionState,
    entities: list[SemanticEntity],
    browser_context: BrowserContext,
) -> dict[str, object]:
    entity_urls = {entity.url for entity in entities if entity.url}
    known_tabs = {tab.get("url") for tab in browser_context.tabs}
    return {
        "mission_goal_count": len(mission_state.goals),
        "entity_count": len(entities),
        "focused_tab_id": browser_context.focused_tab_id,
        "known_tab_count": len(browser_context.tabs),
        "entity_tab_url_overlap": len(entity_urls & known_tabs),
        "canonical_current_url": browser_context.current_url,
    }
