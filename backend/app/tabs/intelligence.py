"""
V6.0 Multi-Tab Coordination Layer — TabIntelligenceAnalyzer.

Deterministic analysis of the tab set for a mission.
ADVISORY ONLY — returns recommendations, never performs actions.
No LLM. No embeddings. No external APIs. Pure rule-based logic.

Findings:
  MISSING_COMPARISON_TAB  — research found but no comparison tab
  MISSING_WORKFLOW_TAB    — mission is ready but no workflow tab open
  DUPLICATE_TABS          — two or more tabs share the same URL
  STALE_TABS              — tabs in BACKGROUND for an unusually long time
  ORPHAN_TABS             — tabs registered but not linked to any mission
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from app.tabs.models import BrowserTab, BrowserTabRole, BrowserTabState
from app.tabs.context import TabContext
from app.tabs import analytics as tab_analytics


# ── Finding types ─────────────────────────────────────────────────────────────

class TabFindingSeverity(str, Enum):
    info     = "INFO"
    warning  = "WARNING"
    critical = "CRITICAL"


@dataclass
class TabFinding:
    """One advisory finding from TabIntelligenceAnalyzer."""
    code:        str               # e.g. "MISSING_COMPARISON_TAB"
    description: str
    severity:    TabFindingSeverity
    tab_ids:     list[str] = field(default_factory=list)   # tabs involved, if any

    def to_dict(self) -> dict:
        return {
            "code":        self.code,
            "description": self.description,
            "severity":    self.severity.value,
            "tab_ids":     self.tab_ids,
        }


@dataclass
class TabIntelligenceResult:
    """
    Advisory analysis of tabs for a mission.
    NEVER mutates state. NEVER triggers actions.
    """
    mission_id:      str
    findings:        list[TabFinding]
    recommendations: list[str]      # human-readable action suggestions
    tab_count:       int
    has_issues:      bool

    def to_dict(self) -> dict:
        return {
            "mission_id":      self.mission_id,
            "findings":        [f.to_dict() for f in self.findings],
            "recommendations": self.recommendations,
            "tab_count":       self.tab_count,
            "has_issues":      self.has_issues,
            "finding_count":   len(self.findings),
        }


# ── Analyzer ──────────────────────────────────────────────────────────────────

_STALE_BACKGROUND_SECONDS = 1800   # 30 minutes

# Readiness threshold for MISSING_WORKFLOW_TAB rule
_READY_SCORE_THRESHOLD = 0.80


class TabIntelligenceAnalyzer:
    """
    Analyze a mission's tab set for structural issues.

    All rules are deterministic. No AI. < 2ms p95.
    """

    def analyze(
        self,
        tab_ctx: TabContext,
        readiness_score: float = 0.0,
    ) -> TabIntelligenceResult:
        """
        Run all advisory rules against the tab context.

        Args:
            tab_ctx:         CrossTabContextBuilder output for the mission.
            readiness_score: Optional V5.5 readiness score (0.0–1.0) for
                             the MISSING_WORKFLOW_TAB rule.

        Returns:
            TabIntelligenceResult (advisory, never mutates state).
        """
        findings: list[TabFinding] = []
        open_tabs = tab_ctx.tab_summaries  # already filtered to open tabs

        # Build lookups for the rule engine
        by_role: dict[str, list[dict]] = {}
        for t in open_tabs:
            role = t["role"]
            by_role.setdefault(role, []).append(t)

        # ── Rule 1: Missing comparison tab ────────────────────────────────────
        research_tabs = by_role.get(BrowserTabRole.research.value, [])
        comparison_tabs = by_role.get(BrowserTabRole.comparison.value, [])
        if len(research_tabs) >= 2 and not comparison_tabs:
            findings.append(TabFinding(
                code="MISSING_COMPARISON_TAB",
                description=(
                    f"{len(research_tabs)} research tabs are open but no comparison tab exists. "
                    "Add a comparison tab to evaluate the options side-by-side."
                ),
                severity=TabFindingSeverity.warning,
                tab_ids=[t["tab_id"] for t in research_tabs],
            ))

        # ── Rule 2: Missing workflow tab ──────────────────────────────────────
        workflow_tabs = by_role.get(BrowserTabRole.workflow.value, [])
        if (
            readiness_score >= _READY_SCORE_THRESHOLD
            and not workflow_tabs
            and open_tabs
        ):
            findings.append(TabFinding(
                code="MISSING_WORKFLOW_TAB",
                description=(
                    f"Mission readiness is {readiness_score:.0%} but no workflow tab is open. "
                    "Open the target site to begin workflow execution."
                ),
                severity=TabFindingSeverity.warning,
            ))

        # ── Rule 3: Duplicate URLs ────────────────────────────────────────────
        if tab_ctx.duplicate_urls:
            dup_tab_ids = [
                t["tab_id"] for t in open_tabs
                if t["url"] in tab_ctx.duplicate_urls
            ]
            findings.append(TabFinding(
                code="DUPLICATE_TABS",
                description=(
                    f"{len(tab_ctx.duplicate_urls)} URL(s) appear on more than one tab. "
                    "Close duplicates to reduce confusion."
                ),
                severity=TabFindingSeverity.info,
                tab_ids=dup_tab_ids,
            ))

        # ── Rule 4: Stale background tabs ─────────────────────────────────────
        stale = self._find_stale_tabs(open_tabs)
        if stale:
            findings.append(TabFinding(
                code="STALE_TABS",
                description=(
                    f"{len(stale)} tab(s) have been in BACKGROUND for "
                    f"over {_STALE_BACKGROUND_SECONDS // 60} minutes. "
                    "Consider closing or refreshing them."
                ),
                severity=TabFindingSeverity.info,
                tab_ids=[t["tab_id"] for t in stale],
            ))

        # ── Rule 5: Orphan tabs ────────────────────────────────────────────────
        orphans = [t for t in open_tabs if not t.get("mission_id")]
        if orphans:
            findings.append(TabFinding(
                code="ORPHAN_TABS",
                description=(
                    f"{len(orphans)} open tab(s) are not linked to any mission. "
                    "Attach them to a mission for tracking."
                ),
                severity=TabFindingSeverity.info,
                tab_ids=[t["tab_id"] for t in orphans],
            ))

        recommendations = self._build_recommendations(findings)
        tab_analytics.record_intelligence_run()

        return TabIntelligenceResult(
            mission_id      = tab_ctx.mission_id,
            findings        = findings,
            recommendations = recommendations,
            tab_count       = tab_ctx.tab_count,
            has_issues      = bool(findings),
        )

    def _find_stale_tabs(self, open_tabs: list[dict]) -> list[dict]:
        """Return tabs that have been BACKGROUND for more than _STALE_BACKGROUND_SECONDS."""
        from datetime import datetime, timezone
        stale = []
        now = datetime.utcnow()
        for t in open_tabs:
            if t.get("state") != BrowserTabState.background.value:
                continue
            try:
                updated_str = t.get("updated_at", "")
                if not updated_str:
                    continue
                # Handle both naive and aware datetimes
                updated = datetime.fromisoformat(updated_str.replace("Z", ""))
                delta = (now - updated).total_seconds()
                if delta > _STALE_BACKGROUND_SECONDS:
                    stale.append(t)
            except (ValueError, TypeError):
                pass
        return stale

    def _build_recommendations(self, findings: list[TabFinding]) -> list[str]:
        recs: list[str] = []
        codes = {f.code for f in findings}
        if "MISSING_COMPARISON_TAB" in codes:
            recs.append("Open a side-by-side comparison tab to evaluate research options.")
        if "MISSING_WORKFLOW_TAB" in codes:
            recs.append("Open the target site tab to begin workflow execution.")
        if "DUPLICATE_TABS" in codes:
            recs.append("Close duplicate tabs to keep the workspace clean.")
        if "STALE_TABS" in codes:
            recs.append("Refresh or close stale background tabs.")
        if "ORPHAN_TABS" in codes:
            recs.append("Attach orphan tabs to a mission for proper tracking.")
        return recs


# Module-level singleton
_analyzer = TabIntelligenceAnalyzer()


def analyze(
    tab_ctx: TabContext,
    readiness_score: float = 0.0,
) -> TabIntelligenceResult:
    return _analyzer.analyze(tab_ctx, readiness_score)
