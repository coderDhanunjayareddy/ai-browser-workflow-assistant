"""
V7.0 Live Browser Sync Layer — RecommendationRefreshEngine.

Produces deterministic DecisionSignals based on mission/trust/tab state.
No LLM. No external calls. Pure rule evaluation.

7 rules (evaluated in order, all independent):
  R1  HIGH/CRITICAL trust risk → WARNING
  R2  approval_required → RECOMMENDATION (request review)
  R3  MISSING_COMPARISON_TAB finding → RECOMMENDATION (open comparison tab)
  R4  ORPHAN_TABS finding → WARNING (unassigned tabs)
  R5  no tabs + mission has tasks → INFO (register tabs to help intelligence)
  R6  readiness_score < 0.40 → WARNING (mission not ready)
  R7  STALE_TABS finding → INFO (some tabs may have old content)
"""
from __future__ import annotations

import time
from typing import Optional

from app.browser.models import DecisionSignal, DecisionSignalType, make_signal

_SOURCE = "RecommendationRefreshEngine"


class RecommendationRefreshEngine:

    def refresh(
        self,
        mission_id: str,
        *,
        intel_report=None,
        trust_ev=None,
        tab_ctx=None,
        tab_findings: Optional[list] = None,
    ) -> list[DecisionSignal]:
        signals: list[DecisionSignal] = []

        # Lazy-load if not provided
        if intel_report is None:
            try:
                from app.mission.intelligence import engine as _intel
                intel_report = _intel.run(mission_id)
            except Exception:
                pass

        if trust_ev is None:
            try:
                from app.trust import mission_analyzer as _ma
                trust_ev = _ma.analyze(mission_id)
            except Exception:
                pass

        if tab_ctx is None:
            try:
                from app.tabs.context import build as _build
                _raw = _build(mission_id)
                tab_ctx = _raw.to_dict()
            except Exception:
                pass

        if tab_findings is None and tab_ctx is not None:
            try:
                from app.tabs.context import build as _build
                from app.tabs.intelligence import analyze as _intel_tabs
                _raw = _build(mission_id)
                _res = _intel_tabs(_raw)
                tab_findings = [f.to_dict() for f in _res.findings]
            except Exception:
                tab_findings = []

        findings_codes = {
            f.get("code", "") for f in (tab_findings or [])
        }

        # R1: HIGH or CRITICAL trust risk → WARNING
        if trust_ev is not None:
            risk = getattr(trust_ev, "risk_level", None)
            if risk and risk.value in ("HIGH", "CRITICAL"):
                signals.append(make_signal(
                    signal_type = DecisionSignalType.warning,
                    target_id   = mission_id,
                    message     = (
                        f"Mission trust risk is {risk.value}. "
                        "Review mission state before proceeding."
                    ),
                    source      = _SOURCE,
                ))

        # R2: approval_required → RECOMMENDATION
        if trust_ev is not None and getattr(trust_ev, "approval_required", False):
            signals.append(make_signal(
                signal_type = DecisionSignalType.recommendation,
                target_id   = mission_id,
                message     = (
                    "This mission requires human approval before execution. "
                    "Review trust score and risk level."
                ),
                source      = _SOURCE,
            ))

        # R3: MISSING_COMPARISON_TAB → RECOMMENDATION
        if "MISSING_COMPARISON_TAB" in findings_codes:
            signals.append(make_signal(
                signal_type = DecisionSignalType.recommendation,
                target_id   = mission_id,
                message     = (
                    "No comparison tab found. "
                    "Opening a comparison tab will improve mission context quality."
                ),
                source      = _SOURCE,
            ))

        # R4: ORPHAN_TABS → WARNING
        if "ORPHAN_TABS" in findings_codes:
            signals.append(make_signal(
                signal_type = DecisionSignalType.warning,
                target_id   = mission_id,
                message     = (
                    "Orphan tabs detected — tabs not assigned to this mission. "
                    "Assign or close them to maintain accurate context."
                ),
                source      = _SOURCE,
            ))

        # R5: no tabs + mission has tasks → INFO
        if tab_ctx is not None and tab_ctx.get("tab_count", 0) == 0:
            has_tasks = False
            if intel_report is not None:
                try:
                    from app.mission import store as _ms
                    m = _ms.get(mission_id)
                    has_tasks = bool(m and m.task_ids)
                except Exception:
                    pass
            if has_tasks:
                signals.append(make_signal(
                    signal_type = DecisionSignalType.info,
                    target_id   = mission_id,
                    message     = (
                        "No browser tabs registered for this mission. "
                        "Opening relevant tabs improves intelligence accuracy."
                    ),
                    source      = _SOURCE,
                ))

        # R6: readiness_score < 0.40 → WARNING
        if intel_report is not None:
            rs = getattr(intel_report, "readiness_score", None)
            if rs is not None and rs < 0.40:
                signals.append(make_signal(
                    signal_type = DecisionSignalType.warning,
                    target_id   = mission_id,
                    message     = (
                        f"Mission readiness is low ({rs:.0%}). "
                        "Resolve blockers and fill information gaps before proceeding."
                    ),
                    source      = _SOURCE,
                ))

        # R7: STALE_TABS → INFO
        if "STALE_TABS" in findings_codes:
            signals.append(make_signal(
                signal_type = DecisionSignalType.info,
                target_id   = mission_id,
                message     = (
                    "Some mission tabs have not been updated recently. "
                    "Refreshing them may improve research quality."
                ),
                source      = _SOURCE,
            ))

        return signals


# ── Module-level singleton ────────────────────────────────────────────────────

_engine = RecommendationRefreshEngine()


def refresh(
    mission_id: str,
    *,
    intel_report=None,
    trust_ev=None,
    tab_ctx=None,
    tab_findings: Optional[list] = None,
) -> list[DecisionSignal]:
    return _engine.refresh(
        mission_id,
        intel_report  = intel_report,
        trust_ev      = trust_ev,
        tab_ctx       = tab_ctx,
        tab_findings  = tab_findings,
    )
