"""
V4.5 / V4.6 Unified Task Graph — TaskAnalytics.

Thread-safe counters for the full task lifecycle.
V4.6 adds: persisted_tasks, restored_tasks, snapshot_count,
           approval_completion_rate, workflow_resume_rate, restoration_latency_ms.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _TaskCounters:
    # V4.5
    total_tasks:                        int   = 0
    active_tasks:                       int   = 0
    completed_tasks:                    int   = 0
    abandoned_tasks:                    int   = 0
    failed_tasks:                       int   = 0
    research_to_workflow_conversions:   int   = 0
    total_approvals:                    int   = 0
    approved_count:                     int   = 0
    denied_count:                       int   = 0
    total_task_duration_ms:             int   = 0
    workflow_completions:               int   = 0
    timeline_events_recorded:          int   = 0
    state_transitions:                  dict  = field(default_factory=dict)
    # V4.6 additions
    persisted_tasks:                    int   = 0   # tasks written to DB
    restored_tasks:                     int   = 0   # tasks restored from DB (cold path)
    restoration_hits:                   int   = 0   # restoration from memory (warm path)
    snapshot_count:                     int   = 0   # snapshots created
    workflow_resumes:                   int   = 0   # workflows resumed after restoration
    total_restoration_latency_ms:       int   = 0   # cumulative restoration latency


_counters = _TaskCounters()
_lock = threading.Lock()


def _reset_for_testing() -> None:
    global _counters
    with _lock:
        _counters = _TaskCounters()


# ── Record helpers ─────────────────────────────────────────────────────────────

def record_task_created() -> None:
    with _lock:
        _counters.total_tasks += 1
        _counters.active_tasks += 1


def record_task_completed(duration_ms: int) -> None:
    with _lock:
        _counters.completed_tasks += 1
        _counters.active_tasks = max(0, _counters.active_tasks - 1)
        _counters.total_task_duration_ms += duration_ms


def record_task_abandoned() -> None:
    with _lock:
        _counters.abandoned_tasks += 1
        _counters.active_tasks = max(0, _counters.active_tasks - 1)


def record_task_failed() -> None:
    with _lock:
        _counters.failed_tasks += 1
        _counters.active_tasks = max(0, _counters.active_tasks - 1)


def record_research_to_workflow() -> None:
    with _lock:
        _counters.research_to_workflow_conversions += 1


def record_approval_requested() -> None:
    with _lock:
        _counters.total_approvals += 1


def record_approval_resolved(approved: bool) -> None:
    with _lock:
        if approved:
            _counters.approved_count += 1
        else:
            _counters.denied_count += 1


def record_workflow_completion() -> None:
    with _lock:
        _counters.workflow_completions += 1


def record_timeline_event(event_type: str = "") -> None:
    with _lock:
        _counters.timeline_events_recorded += 1


def record_state_transition(from_state: str, to_state: str) -> None:
    key = f"{from_state}->{to_state}"
    with _lock:
        _counters.state_transitions[key] = _counters.state_transitions.get(key, 0) + 1


# ── V4.6 record helpers ───────────────────────────────────────────────────────

def record_persisted_task() -> None:
    with _lock:
        _counters.persisted_tasks += 1


def record_restored_task(latency_ms: int = 0) -> None:
    with _lock:
        _counters.restored_tasks += 1
        _counters.total_restoration_latency_ms += latency_ms


def record_restoration_hit(latency_ms: int = 0) -> None:
    with _lock:
        _counters.restoration_hits += 1
        _counters.total_restoration_latency_ms += latency_ms


def record_snapshot_created() -> None:
    with _lock:
        _counters.snapshot_count += 1


def record_workflow_resumed() -> None:
    with _lock:
        _counters.workflow_resumes += 1


# ── Read ───────────────────────────────────────────────────────────────────────

def get_analytics() -> dict[str, Any]:
    with _lock:
        completed = _counters.completed_tasks
        total = _counters.total_tasks
        approvals = _counters.total_approvals
        approved = _counters.approved_count

        avg_duration_ms = (
            _counters.total_task_duration_ms // completed
            if completed > 0 else 0
        )
        research_to_wf_rate = (
            _counters.research_to_workflow_conversions / total
            if total > 0 else 0.0
        )
        approval_rate = (
            approved / approvals
            if approvals > 0 else 0.0
        )
        completion_rate = (
            _counters.workflow_completions / total
            if total > 0 else 0.0
        )

        total_restorations = _counters.restored_tasks + _counters.restoration_hits
        avg_restoration_ms = (
            _counters.total_restoration_latency_ms // total_restorations
            if total_restorations > 0 else 0
        )
        approval_completion = (
            (_counters.approved_count + _counters.denied_count) / _counters.total_approvals
            if _counters.total_approvals > 0 else 0.0
        )
        workflow_resume_rate = (
            _counters.workflow_resumes / _counters.restored_tasks
            if _counters.restored_tasks > 0 else 0.0
        )

        return {
            "total_tasks":                      _counters.total_tasks,
            "active_tasks":                     _counters.active_tasks,
            "completed_tasks":                  _counters.completed_tasks,
            "abandoned_tasks":                  _counters.abandoned_tasks,
            "failed_tasks":                     _counters.failed_tasks,
            "research_to_workflow_conversion":  _counters.research_to_workflow_conversions,
            "research_to_workflow_rate":        round(research_to_wf_rate, 3),
            "approval_rate":                    round(approval_rate, 3),
            "average_task_duration_ms":         avg_duration_ms,
            "workflow_completion_rate":         round(completion_rate, 3),
            "workflow_completions":             _counters.workflow_completions,
            "total_approvals":                  _counters.total_approvals,
            "approved_count":                   _counters.approved_count,
            "denied_count":                     _counters.denied_count,
            "timeline_events_recorded":         _counters.timeline_events_recorded,
            "state_transitions":                dict(_counters.state_transitions),
            # V4.6
            "persisted_tasks":                  _counters.persisted_tasks,
            "restored_tasks":                   _counters.restored_tasks,
            "restoration_hits":                 _counters.restoration_hits,
            "snapshot_count":                   _counters.snapshot_count,
            "workflow_resumes":                 _counters.workflow_resumes,
            "average_restoration_latency_ms":   avg_restoration_ms,
            "approval_completion_rate":         round(approval_completion, 3),
            "workflow_resume_rate":             round(workflow_resume_rate, 3),
        }
