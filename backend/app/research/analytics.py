"""
Research analytics counters.

In-memory only — resets on server restart. Same design pattern as
cognitive_core/analytics.py. Persisted metrics live in the session records.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

_lock = threading.Lock()


@dataclass
class _ResearchCounters:
    sessions_started: int = 0
    sessions_completed: int = 0
    sessions_failed: int = 0
    sources_collected: int = 0
    syntheses_run: int = 0
    workflow_escalations: int = 0
    page_context_uses: int = 0
    ddg_uses: int = 0
    ai_knowledge_uses: int = 0
    # V4.0 Intelligence Layer extensions
    intelligence_runs: int = 0
    execution_opportunities_detected: int = 0
    execution_recommendations_generated: int = 0
    blocked_workflows: int = 0
    workflow_conversions: int = 0


_counters = _ResearchCounters()


def record_session_started() -> None:
    with _lock:
        _counters.sessions_started += 1


def record_session_completed() -> None:
    with _lock:
        _counters.sessions_completed += 1


def record_session_failed() -> None:
    with _lock:
        _counters.sessions_failed += 1


def record_sources(
    count: int,
    used_page_context: bool = False,
    used_ddg: bool = False,
    used_ai_knowledge: bool = False,
) -> None:
    with _lock:
        _counters.sources_collected += count
        if used_page_context:
            _counters.page_context_uses += 1
        if used_ddg:
            _counters.ddg_uses += 1
        if used_ai_knowledge:
            _counters.ai_knowledge_uses += 1


def record_synthesis() -> None:
    with _lock:
        _counters.syntheses_run += 1


def record_workflow_escalation() -> None:
    with _lock:
        _counters.workflow_escalations += 1


# ── V4.0 Intelligence Layer extensions ───────────────────────────────────────

def record_intelligence_run(
    opportunity_detected: bool,
    recommendation_count: int,
    is_blocked: bool,
) -> None:
    with _lock:
        _counters.intelligence_runs += 1
        if opportunity_detected:
            _counters.execution_opportunities_detected += 1
        _counters.execution_recommendations_generated += recommendation_count
        if is_blocked:
            _counters.blocked_workflows += 1


def record_workflow_conversion() -> None:
    with _lock:
        _counters.workflow_conversions += 1


def get_analytics() -> dict:
    with _lock:
        return {
            "sessions_started": _counters.sessions_started,
            "sessions_completed": _counters.sessions_completed,
            "sessions_failed": _counters.sessions_failed,
            "sources_collected": _counters.sources_collected,
            "syntheses_run": _counters.syntheses_run,
            "workflow_escalations": _counters.workflow_escalations,
            "provider_uses": {
                "page_context": _counters.page_context_uses,
                "duckduckgo": _counters.ddg_uses,
                "ai_knowledge": _counters.ai_knowledge_uses,
            },
            "intelligence_layer": {
                "intelligence_runs": _counters.intelligence_runs,
                "execution_opportunities_detected": _counters.execution_opportunities_detected,
                "execution_recommendations_generated": _counters.execution_recommendations_generated,
                "blocked_workflows": _counters.blocked_workflows,
                "workflow_conversions": _counters.workflow_conversions,
            },
        }


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _ResearchCounters()
