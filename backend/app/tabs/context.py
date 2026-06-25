"""
V6.0 Multi-Tab Coordination Layer — CrossTabContextBuilder.

Aggregates all tab metadata for a mission into a single TabContext object.
No DOM extraction. No screenshots. Metadata only.

Used by:
  - Mission Intelligence Engine (V5.5 extension)
  - Mission Bootstrap (V5.0 extension)
  - Mission Inspector (V5.0 extension)
  - REST API /tabs/inspect/{mission_id}

Performance: all operations are in-memory scans over TabRegistry. < 10ms p95.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from app.tabs.models import BrowserTab, BrowserTabRole, BrowserTabState
from app.tabs import registry as tab_registry
from app.tabs import analytics as tab_analytics


@dataclass
class TabContext:
    """
    Aggregated cross-tab context for a mission.
    Advisory only — read-only view.
    """
    mission_id:               str
    tab_count:                int
    active_tab_count:         int
    tab_summaries:            list[dict]         # [{tab_id, url, title, role, state}]
    roles_present:            list[str]          # unique BrowserTabRole values
    primary_tab:              Optional[dict]     # summary of PRIMARY tab, or None
    active_tab:               Optional[dict]     # summary of ACTIVE tab, or None
    workflow_tab_present:     bool
    comparison_tab_present:   bool
    research_tab_present:     bool
    duplicate_urls:           list[str]          # URLs that appear on 2+ tabs
    latency_ms:               int = 0

    def to_dict(self) -> dict:
        return {
            "mission_id":             self.mission_id,
            "tab_count":              self.tab_count,
            "active_tab_count":       self.active_tab_count,
            "tab_summaries":          self.tab_summaries,
            "roles_present":          self.roles_present,
            "primary_tab":            self.primary_tab,
            "active_tab":             self.active_tab,
            "workflow_tab_present":   self.workflow_tab_present,
            "comparison_tab_present": self.comparison_tab_present,
            "research_tab_present":   self.research_tab_present,
            "duplicate_urls":         self.duplicate_urls,
            "latency_ms":             self.latency_ms,
        }


class CrossTabContextBuilder:
    """
    Builds a TabContext for a mission from the global TabRegistry.
    Pure in-memory. No DB calls. No AI calls.
    """

    def build(self, mission_id: str) -> TabContext:
        """
        Aggregate all open tab metadata for a mission.

        Returns a TabContext even if there are zero tabs (all fields default).
        """
        t0 = time.perf_counter()

        open_tabs: list[BrowserTab] = tab_registry.open_for_mission(mission_id)

        tab_summaries = [t.to_summary() for t in open_tabs]
        active_tabs   = [t for t in open_tabs if t.state == BrowserTabState.active]
        roles_present = list({t.role.value for t in open_tabs})

        # Primary tab: first PRIMARY-role tab
        primary = next(
            (t for t in open_tabs if t.role == BrowserTabRole.primary), None
        )

        # Active tab: the single ACTIVE one (there should be at most one)
        active = active_tabs[0] if active_tabs else None

        # Role presence flags
        workflow_present   = any(t.role == BrowserTabRole.workflow   for t in open_tabs)
        comparison_present = any(t.role == BrowserTabRole.comparison for t in open_tabs)
        research_present   = any(t.role == BrowserTabRole.research   for t in open_tabs)

        # Duplicate URL detection (same URL on 2+ different tabs)
        url_counts: dict[str, int] = {}
        for t in open_tabs:
            if t.url:
                url_counts[t.url] = url_counts.get(t.url, 0) + 1
        duplicate_urls = [url for url, cnt in url_counts.items() if cnt > 1]

        latency_ms = int((time.perf_counter() - t0) * 1000)
        tab_analytics.record_context_build(latency_ms)

        return TabContext(
            mission_id             = mission_id,
            tab_count              = len(open_tabs),
            active_tab_count       = len(active_tabs),
            tab_summaries          = tab_summaries,
            roles_present          = roles_present,
            primary_tab            = primary.to_summary() if primary else None,
            active_tab             = active.to_summary() if active else None,
            workflow_tab_present   = workflow_present,
            comparison_tab_present = comparison_present,
            research_tab_present   = research_present,
            duplicate_urls         = duplicate_urls,
            latency_ms             = latency_ms,
        )


# Module-level singleton
_builder = CrossTabContextBuilder()


def build(mission_id: str) -> TabContext:
    return _builder.build(mission_id)
