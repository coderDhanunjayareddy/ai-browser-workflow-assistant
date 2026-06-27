"""
V5.0 Mission Layer — REST API routes.

Endpoints:
  POST   /mission/                          → create mission
  GET    /mission/                          → list all active missions
  GET    /mission/analytics                 → mission analytics
  POST   /mission/assign                    → auto-assign task to mission
  GET    /mission/{mission_id}              → get mission details
  PATCH  /mission/{mission_id}/state        → update state (pause/resume/complete/fail/abandon)
  DELETE /mission/{mission_id}              → delete mission
  POST   /mission/{mission_id}/tasks/{task_id} → attach task
  DELETE /mission/{mission_id}/tasks/{task_id} → detach task
  GET    /mission/{mission_id}/timeline     → merged timeline
  GET    /mission/{mission_id}/context      → aggregated mission context
  GET    /mission/{mission_id}/memory       → mission memory
  GET    /mission/{mission_id}/restore      → restore mission from DB
  GET    /mission/{mission_id}/bootstrap/{task_id} → enriched workflow bootstrap
  GET    /mission/{mission_id}/inspect      → full inspector view
"""
import time
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.mission import (
    store     as mission_store,
    lifecycle as mission_lifecycle,
    timeline  as mission_timeline,
    context_registry,
    memory    as mission_memory,
    analytics as mission_analytics,
    restoration as mission_restoration,
    bootstrap as mission_bootstrap,
    affinity  as mission_affinity,
)
from app.schemas.mission import (
    MissionSchema,
    MissionTimelineEventSchema,
    MissionContextSchema,
    MissionMemorySchema,
    MissionAnalyticsSchema,
    MissionBootstrapSchema,
    MissionAssignSchema,
    MissionInspectorSchema,
    MissionTaskSummarySchema,
    CreateMissionRequest,
    AssignTaskRequest,
)
from app.mission.models import Mission

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/mission", tags=["mission"])


# ── Serialization helpers ─────────────────────────────────────────────────────

def _mission_schema(mission: Mission) -> MissionSchema:
    return MissionSchema(
        mission_id=mission.mission_id,
        title=mission.title,
        objective=mission.objective,
        state=mission.state.value,
        priority=mission.priority,
        task_ids=list(mission.task_ids),
        task_count=len(mission.task_ids),
        metadata=mission.metadata,
        created_at=mission.created_at.isoformat(),
        updated_at=mission.updated_at.isoformat(),
    )


def _memory_schema(mem) -> MissionMemorySchema:
    return MissionMemorySchema(
        mission_id=mem.mission_id,
        entities=mem.entities,
        goals=mem.goals,
        research_findings=mem.research_findings,
        execution_plans=mem.execution_plans,
        decisions=mem.decisions,
        last_updated=mem.last_updated.isoformat(),
    )


def _context_schema(ctx) -> MissionContextSchema:
    task_summaries = [
        MissionTaskSummarySchema(
            task_id=ts["task_id"],
            state=ts["state"],
            query=ts["query"] or "",
            goal=ts.get("goal"),
            has_research=ts["has_research"],
            has_plan=ts["has_plan"],
            approval_count=ts["approval_count"],
        )
        for ts in ctx.task_summaries
    ]
    return MissionContextSchema(
        mission_id=ctx.mission_id,
        mission_title=ctx.mission_title,
        mission_state=ctx.mission_state,
        priority=ctx.priority,
        task_count=ctx.task_count,
        task_summaries=task_summaries,
        entities=ctx.entities,
        goals=ctx.goals,
        research_findings=ctx.research_findings,
        execution_plans=ctx.execution_plans,
        approvals=ctx.approvals,
        memory=_memory_schema(ctx.memory),
        latency_ms=ctx.latency_ms,
    )


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/", response_model=MissionSchema)
def create_mission(body: CreateMissionRequest):
    """Create a new mission."""
    mission = mission_lifecycle.create_mission_obj(
        title=body.title,
        objective=body.objective or body.title,
        priority=body.priority,
    )
    mission.metadata.update(body.metadata)
    return _mission_schema(mission)


@router.get("/", response_model=list[MissionSchema])
def list_missions(include_terminal: bool = False):
    """Return all active missions (or all including terminal when flag is set)."""
    missions = mission_store.all_missions() if include_terminal else mission_store.active_missions()
    return [_mission_schema(m) for m in missions]


@router.get("/analytics", response_model=MissionAnalyticsSchema)
def get_analytics():
    return MissionAnalyticsSchema(**mission_analytics.get_analytics())


@router.post("/assign", response_model=MissionAssignSchema)
def assign_task(body: AssignTaskRequest):
    """Auto-assign a task to the best-matching mission (or create one)."""
    from app.unified import store as task_store
    task = task_store.get(body.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {body.task_id!r} not found")

    # Check for existing match before assignment (to know if we created one)
    pre_match = mission_affinity.find_matching_mission(task)
    mission = mission_affinity.assign_task_to_mission(task, create_if_none=body.create_if_none)

    if mission is None:
        raise HTTPException(status_code=404, detail="No matching mission found and create_if_none=false")

    return MissionAssignSchema(
        task_id=body.task_id,
        mission_id=mission.mission_id,
        mission_title=mission.title,
        was_created=pre_match is None,
        affinity_score=mission_affinity.score_pair(task.original_query, mission.objective)
            if pre_match else None,
    )


@router.get("/{mission_id}", response_model=MissionSchema)
def get_mission(mission_id: str):
    mission = mission_store.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    return _mission_schema(mission)


class StateUpdateRequest(BaseModel):
    action: str            # pause | resume | complete | fail | abandon
    reason: Optional[str] = ""


@router.patch("/{mission_id}/state", response_model=MissionSchema)
def update_state(mission_id: str, body: StateUpdateRequest):
    """Transition mission state."""
    action = body.action.lower()
    valid_actions = {"pause", "resume", "complete", "fail", "abandon"}
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Unknown action {action!r}")
    try:
        if action == "pause":
            mission = mission_lifecycle.pause(mission_id)
        elif action == "resume":
            mission = mission_lifecycle.resume(mission_id)
        elif action == "complete":
            mission = mission_lifecycle.complete(mission_id)
        elif action == "fail":
            mission = mission_lifecycle.fail(mission_id, body.reason or "")
        else:
            mission = mission_lifecycle.abandon(mission_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _mission_schema(mission)


@router.delete("/{mission_id}", response_model=dict)
def delete_mission(mission_id: str):
    mission = mission_store.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    mission_store.remove(mission_id)
    from app.mission import persistence as mission_persistence
    mission_persistence.delete(mission_id)
    return {"deleted": True, "mission_id": mission_id}


@router.post("/{mission_id}/tasks/{task_id}", response_model=MissionSchema)
def attach_task(mission_id: str, task_id: str):
    try:
        mission = mission_lifecycle.attach_task(mission_id, task_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _mission_schema(mission)


@router.delete("/{mission_id}/tasks/{task_id}", response_model=MissionSchema)
def detach_task(mission_id: str, task_id: str):
    try:
        mission = mission_lifecycle.detach_task(mission_id, task_id)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _mission_schema(mission)


@router.get("/{mission_id}/timeline", response_model=list[MissionTimelineEventSchema])
def get_timeline(mission_id: str):
    mission = mission_store.get(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")

    from app.unified import store as task_store
    tasks = [t for tid in mission.task_ids if (t := task_store.get(tid)) is not None]
    events = mission_timeline.build(mission, tasks)

    return [
        MissionTimelineEventSchema(
            event_id=ev.event_id,
            event_type=ev.event_type.value,
            mission_id=ev.mission_id,
            task_id=ev.task_id,
            data=ev.data,
            timestamp=ev.timestamp.isoformat(),
        )
        for ev in events
    ]


@router.get("/{mission_id}/context", response_model=MissionContextSchema)
def get_context(mission_id: str):
    ctx = context_registry.get_context(mission_id)
    if ctx is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    return _context_schema(ctx)


@router.get("/{mission_id}/memory", response_model=MissionMemorySchema)
def get_memory(mission_id: str):
    mem = mission_memory.build_by_id(mission_id)
    if mem is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")
    return _memory_schema(mem)


@router.get("/{mission_id}/restore", response_model=MissionSchema)
def restore_mission(mission_id: str):
    """Restore a mission (and its tasks) from DB into the in-memory store."""
    mission = mission_restoration.restore(mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found in store or DB")
    return _mission_schema(mission)


@router.get("/{mission_id}/bootstrap/{task_id}", response_model=MissionBootstrapSchema)
def get_bootstrap(mission_id: str, task_id: str):
    """Return a mission-enriched workflow bootstrap for a specific task."""
    result = mission_bootstrap.enrich_task_bootstrap(task_id=task_id, mission_id=mission_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Mission or task not found")
    return MissionBootstrapSchema(
        mission_id=result.mission_id,
        task_id=result.task_id,
        is_ready=result.is_ready,
        mission_entity_count=result.mission_entity_count,
        mission_goal_count=result.mission_goal_count,
        mission_research_count=result.mission_research_count,
        merged_entities=result.merged_entities,
        merged_goals=result.merged_goals,
        enriched_facts=result.enriched_facts,
        latency_ms=result.latency_ms,
    )


@router.get("/{mission_id}/inspect", response_model=MissionInspectorSchema)
def inspect_mission(mission_id: str):
    """Full inspector view: mission + context + memory + timeline."""
    t0 = time.perf_counter()
    mission = mission_store.get(mission_id)
    from_store = True

    if mission is None:
        mission = mission_restoration.restore(mission_id)
        from_store = False

    if mission is None:
        raise HTTPException(status_code=404, detail=f"Mission {mission_id!r} not found")

    # Context
    ctx = context_registry.get_context(mission_id)
    context_s = _context_schema(ctx) if ctx else None

    # Memory
    mem = mission_memory.build_by_id(mission_id)
    memory_s = _memory_schema(mem) if mem else None

    # Timeline
    from app.unified import store as task_store
    tasks = [t for tid in mission.task_ids if (t := task_store.get(tid)) is not None]
    events = mission_timeline.build(mission, tasks)
    timeline_s = [
        MissionTimelineEventSchema(
            event_id=ev.event_id,
            event_type=ev.event_type.value,
            mission_id=ev.mission_id,
            task_id=ev.task_id,
            data=ev.data,
            timestamp=ev.timestamp.isoformat(),
        )
        for ev in events
    ]

    # Intelligence (V5.5 advisory section — non-blocking if unavailable)
    intel_section: Optional[dict] = None
    try:
        from app.mission.intelligence import engine as _intel_engine
        intel_report = _intel_engine.run(mission_id)
        if intel_report is not None:
            intel_section = {
                "readiness_score":    intel_report.readiness_score,
                "advisory_state":     intel_report.advisory_state.value,
                "confidence":         intel_report.confidence,
                "recommended_action": intel_report.recommended_action,
                "suggested_workflow": intel_report.suggested_workflow,
                "blocker_count":      len(intel_report.blockers),
                "critical_blockers":  [b.code for b in intel_report.critical_blockers],
                "next_action":        intel_report.next_action.action,
                "reasoning":          intel_report.reasoning,
            }
    except Exception:
        pass  # Intelligence is advisory — inspect never fails because of it

    # Tab coordination (V6.0 section — non-blocking if unavailable)
    tabs_section: Optional[dict] = None
    try:
        from app.tabs.context import build as _build_tab_ctx
        from app.tabs.intelligence import analyze as _analyze_tabs
        from app.tabs import mission_tab_map as _mtm
        tab_ctx    = _build_tab_ctx(mission_id)
        intel_res  = _analyze_tabs(tab_ctx)
        tabs_section = {
            "tab_count":              tab_ctx.tab_count,
            "active_tab_count":       tab_ctx.active_tab_count,
            "workflow_tab_present":   tab_ctx.workflow_tab_present,
            "comparison_tab_present": tab_ctx.comparison_tab_present,
            "research_tab_present":   tab_ctx.research_tab_present,
            "roles_present":          tab_ctx.roles_present,
            "active_tab":             tab_ctx.active_tab,
            "tab_summaries":          tab_ctx.tab_summaries,
            "findings":               [f.to_dict() for f in intel_res.findings],
            "recommendations":        intel_res.recommendations,
        }
    except Exception:
        pass  # Tab coordination is optional — inspect never fails because of it

    # Trust evaluation (V6.5 section — non-blocking if unavailable)
    trust_section: Optional[dict] = None
    try:
        from app.trust import mission_analyzer as _trust_ma
        from app.unified import store as _task_store_trust
        from app.unified.models import TaskState as _TaskState_trust
        _all_tasks_t = [_task_store_trust.get(tid) for tid in mission.task_ids
                        if _task_store_trust.get(tid) is not None]
        _completed_t = sum(1 for t in _all_tasks_t
                           if t and t.state == _TaskState_trust.completed)
        _failed_t    = sum(1 for t in _all_tasks_t
                           if t and t.state == _TaskState_trust.failed)
        _rs = intel_section.get("readiness_score", 0.0) if intel_section else 0.0
        _bc = intel_section.get("blocker_count", 0)     if intel_section else 0
        _tc = tabs_section.get("tab_count", 0)          if tabs_section  else 0
        _wf = tabs_section.get("workflow_tab_present", False) if tabs_section else False
        _trust_ev = _trust_ma.analyze(
            mission_id            = mission_id,
            readiness_score       = _rs,
            critical_blockers     = _bc,
            task_count            = len(_all_tasks_t),
            completed_task_count  = _completed_t,
            failed_task_count     = _failed_t,
            tab_count             = _tc,
            workflow_tab_present  = _wf,
        )
        trust_section = {
            "trust_score":       round(_trust_ev.trust_score, 3),
            "risk_level":        _trust_ev.risk_level.value,
            "approval_required": _trust_ev.approval_required,
            "confidence":        round(_trust_ev.confidence, 3),
            "reasoning":         _trust_ev.reasoning,
        }
    except Exception:
        pass  # Trust is advisory — inspect never fails because of it

    # V7.5: Decision summary (non-blocking)
    decision_summary = None
    try:
        from app.decisions import feed as _dec_feed
        decision_summary = _dec_feed.summary_for_mission(mission_id)
    except Exception:
        pass

    # V8.0: Approval summary (non-blocking)
    approval_summary = None
    try:
        from app.approvals import queue as _appr_queue
        approval_summary = _appr_queue.summary_for_mission(mission_id)
    except Exception:
        pass

    # V8.5: Governance summary (non-blocking)
    governance_summary = None
    try:
        from app.governance import registry as _gov_reg
        governance_summary = _gov_reg.summary_for_mission(mission_id)
    except Exception:
        pass

    # V8.8: Authorization summary (non-blocking)
    authorization_summary = None
    try:
        from app.authorization import registry as _auth_reg
        authorization_summary = _auth_reg.summary_for_mission(mission_id)
    except Exception:
        pass

    # V8.9: Browser runtime summary (non-blocking)
    runtime_summary = None
    try:
        from app.runtime import registry as _rt_reg
        from app.runtime import cache as _rt_cache
        from app.runtime import events as _rt_events
        rt = _rt_reg.summary_for_mission(mission_id)
        primary = rt["runtime_ids"][0] if rt.get("runtime_ids") else None
        runtime_summary = {
            "active_tab_id":     rt.get("active_tab_id"),
            "runtime_health": {
                "total_sessions":  rt.get("total_sessions", 0),
                "active_sessions": rt.get("active_sessions", 0),
            },
            "cache_health": {
                "has_context": bool(primary and _rt_cache.peek(primary) is not None),
                "is_fresh":    bool(primary and _rt_cache.is_fresh(primary)),
                "age_seconds": _rt_cache.age_seconds(primary) if primary else None,
            },
            "event_count":       _rt_events.count_for_runtime(primary) if primary else 0,
            "context_freshness": _rt_cache.age_seconds(primary) if primary else None,
        }
    except Exception:
        pass

    # V9.0: Execution planning summary (non-blocking)
    execution_planning_summary = None
    try:
        from app.execution_planning import registry as _plan_reg
        ep = _plan_reg.summary_for_mission(mission_id)
        active_plan = None
        if ep.get("active_plan_id"):
            active_plan = _plan_reg.get(ep["active_plan_id"])
        execution_planning_summary = {
            "active_plan_id":     ep.get("active_plan_id"),
            "plan_readiness":     (active_plan.status.value if active_plan else None),
            "total_plans":        ep.get("total_plans", 0),
            "ready_plans":        ep.get("ready_plans", 0),
            "estimated_steps":    (active_plan.estimated_steps if active_plan else 0),
            "estimated_duration_ms": (active_plan.estimated_duration_ms if active_plan else 0),
            "rollback_available": (active_plan.rollback_supported if active_plan else False),
        }
    except Exception:
        pass

    # Phase B: Execution gateway summary (non-blocking)
    execution_gateway_summary = None
    try:
        from app.execution_gateway import registry as _gw_reg
        execution_gateway_summary = _gw_reg.summary_for_mission(mission_id)
    except Exception:
        pass

    latency_ms = int((time.perf_counter() - t0) * 1000)

    return MissionInspectorSchema(
        mission_id=mission_id,
        mission=_mission_schema(mission),
        context=context_s,
        memory=memory_s,
        timeline=timeline_s,
        intelligence=intel_section,
        tabs=tabs_section,
        trust=trust_section,
        decisions=decision_summary,
        approvals=approval_summary,
        governance=governance_summary,
        authorization=authorization_summary,
        runtime=runtime_summary,
        execution_planning=execution_planning_summary,
        execution_gateway=execution_gateway_summary,
        from_store=from_store,
        latency_ms=latency_ms,
    )
