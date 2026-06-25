"""
V5.0 Mission Layer — MissionBootstrap.

Enriches a task's WorkflowBootstrapContext with mission-level intelligence.
Wraps the existing WorkflowBootstrapConsumer (from app/unified/bootstrap_consumer.py)
so mission context (entities, goals, research) is merged into the handoff payload
before the workflow engine receives it.

No LLM required. Deterministic merge only.
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass
from typing import Optional

from app.mission.models import Mission
from app.mission import store as mission_store

logger = logging.getLogger(__name__)


@dataclass
class MissionBootstrapResult:
    mission_id:            str
    task_id:               str
    is_ready:              bool
    mission_entity_count:  int
    mission_goal_count:    int
    mission_research_count: int
    merged_entities:       dict
    merged_goals:          list[str]
    enriched_facts:        dict
    latency_ms:            int


def enrich_task_bootstrap(task_id: str, mission_id: str) -> Optional[MissionBootstrapResult]:
    """
    Retrieve the mission's aggregated context and merge it into the task's
    workflow bootstrap payload.

    Returns None if the mission or task is not found.
    """
    from app.unified import store as task_store, bootstrap_consumer
    from app.mission import memory as mission_memory

    t0 = time.perf_counter()

    mission = mission_store.get(mission_id)
    if mission is None:
        return None

    task = task_store.get(task_id)
    if task is None:
        return None

    # Build the base bootstrap from the task
    consumer = bootstrap_consumer.WorkflowBootstrapConsumer()
    base = consumer.consume(task)

    # Build mission memory (all tasks in mission)
    all_tasks = [
        t for tid in mission.task_ids if (t := task_store.get(tid)) is not None
    ]
    mem = mission_memory.build(mission, all_tasks)

    # Merge mission entities into task entities (mission context wins on conflict)
    merged_entities = {**base.entities, **mem.entities}

    # Merge goals: task goal first (most specific), then mission-wide goals
    merged_goals: list[str] = []
    if task.current_goal and task.current_goal not in merged_goals:
        merged_goals.append(task.current_goal)
    for goal in mem.goals:
        if goal not in merged_goals:
            merged_goals.append(goal)

    # Build enriched_facts for the workflow handoff payload
    enriched_facts = {
        **base.as_bootstrap_facts(),
        "mission_id":             mission_id,
        "mission_title":          mission.title,
        "mission_objective":      mission.objective,
        "mission_entities":       mem.entities,
        "mission_goals":          mem.goals,
        "mission_research_count": len(mem.research_findings),
        "mission_plan_count":     len(mem.execution_plans),
        "mission_decisions":      mem.decisions,
    }

    # V5.5: Append advisory intelligence fields (non-blocking — silently skipped on error)
    try:
        from app.mission.intelligence import engine as _intel_engine
        intel = _intel_engine.run(mission_id)
        if intel is not None:
            enriched_facts.update({
                "mission_readiness_score":    intel.readiness_score,
                "mission_advisory_state":     intel.advisory_state.value,
                "mission_recommended_action": intel.recommended_action,
                "mission_suggested_workflow": intel.suggested_workflow,
                "mission_blocker_count":      len(intel.blockers),
            })
    except Exception:
        pass

    # V6.0: Append tab coordination context (non-blocking — silently skipped on error)
    try:
        from app.tabs.context import build as _build_tab_ctx
        tab_ctx = _build_tab_ctx(mission_id)
        enriched_facts.update({
            "mission_tab_count":              tab_ctx.tab_count,
            "mission_active_tab_count":       tab_ctx.active_tab_count,
            "mission_workflow_tab_present":   tab_ctx.workflow_tab_present,
            "mission_comparison_tab_present": tab_ctx.comparison_tab_present,
            "mission_research_tab_present":   tab_ctx.research_tab_present,
        })
        if tab_ctx.active_tab:
            enriched_facts["mission_active_tab_url"] = tab_ctx.active_tab.get("url", "")
    except Exception:
        pass

    # V6.5: Append trust evaluation fields (non-blocking — silently skipped on error)
    try:
        from app.trust import mission_analyzer as _trust_ma
        from app.unified.models import TaskState as _TaskState
        _all_tasks = [
            t for tid in mission.task_ids if (t := task_store.get(tid)) is not None
        ]
        _completed = sum(1 for t in _all_tasks if t.state == _TaskState.completed)
        _failed    = sum(1 for t in _all_tasks if t.state == _TaskState.failed)
        _trust_ev = _trust_ma.analyze(
            mission_id           = mission_id,
            readiness_score      = enriched_facts.get("mission_readiness_score", 0.0),
            critical_blockers    = enriched_facts.get("mission_blocker_count", 0),
            task_count           = len(_all_tasks),
            completed_task_count = _completed,
            failed_task_count    = _failed,
            tab_count            = enriched_facts.get("mission_tab_count", 0),
            workflow_tab_present = enriched_facts.get("mission_workflow_tab_present", False),
        )
        enriched_facts.update({
            "mission_trust_score":       round(_trust_ev.trust_score, 3),
            "mission_risk_level":        _trust_ev.risk_level.value,
            "mission_approval_required": _trust_ev.approval_required,
        })
    except Exception:
        pass

    latency_ms = int((time.perf_counter() - t0) * 1000)

    return MissionBootstrapResult(
        mission_id=mission_id,
        task_id=task_id,
        is_ready=base.is_ready,
        mission_entity_count=len(mem.entities),
        mission_goal_count=len(mem.goals),
        mission_research_count=len(mem.research_findings),
        merged_entities=merged_entities,
        merged_goals=merged_goals,
        enriched_facts=enriched_facts,
        latency_ms=latency_ms,
    )


def enrich_handoff_payload(payload: dict, mission_id: str) -> dict:
    """
    Merge mission context into an existing handoff payload dict.
    Safe to call even if mission_id is unknown (returns payload unchanged).
    """
    mission = mission_store.get(mission_id)
    if mission is None:
        return payload

    from app.mission import memory as mission_memory
    from app.unified import store as task_store

    all_tasks = [
        t for tid in mission.task_ids if (t := task_store.get(tid)) is not None
    ]
    mem = mission_memory.build(mission, all_tasks)

    enriched = {**payload}
    enriched.setdefault("mission_id", mission_id)
    enriched.setdefault("mission_title", mission.title)

    # Merge mission entities on top of task entities
    existing_entities = enriched.get("pre_filled_facts", {})
    if isinstance(existing_entities, dict):
        enriched["pre_filled_facts"] = {**existing_entities, **mem.entities}

    enriched.setdefault("mission_goals", mem.goals)
    enriched.setdefault("mission_research_findings", mem.research_findings)
    return enriched
