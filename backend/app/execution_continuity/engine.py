from __future__ import annotations

import time
from typing import Any

from app.execution_continuity.action_history import build_action_history
from app.execution_continuity.mission_progress import MissionProgressTracker
from app.execution_continuity.models import ContinuitySnapshot
from app.execution_continuity.progress_validator import validate_progress
from app.execution_continuity.replay import build_replay_frames
from app.execution_continuity.replanner import apply_continuity_replanner
from app.execution_continuity.tab_state import build_browser_state
from app.execution_continuity.telemetry import build_telemetry
from app.execution_continuity.workflow_state import ContinuityStateStore
from app.feature_flags import is_active, is_shadow_or_active
from app.schemas.response import AnalyzeResponse


class ExecutionContinuityEngine:
    def __init__(self) -> None:
        self.mission_tracker = MissionProgressTracker()
        self.store = ContinuityStateStore()

    def observe(
        self,
        *,
        session_id: str,
        task: str,
        page_context: Any,
        prior_steps: list[Any],
    ) -> ContinuitySnapshot | None:
        if not is_shadow_or_active("V47_EXECUTION_CONTINUITY"):
            return None
        started = time.perf_counter()
        records = build_action_history(prior_steps)
        mission = self.mission_tracker.build(task, prior_steps)
        browser_state = build_browser_state(page_context, prior_steps)
        validation = validate_progress(records, mission)
        replay_frames = build_replay_frames(records)
        telemetry = build_telemetry(
            started_at=started,
            records=records,
            mission=mission,
            validation=validation,
        )
        snapshot = ContinuitySnapshot(
            schema_version="execution_continuity.v1",
            session_id=session_id,
            mission=mission,
            browser_state=browser_state,
            recent_actions=records[-12:],
            progress_validation=validation,
            telemetry=telemetry,
            replay_frames=replay_frames,
        )
        self.store.save(snapshot)
        return snapshot

    def enrich_context(self, compressed_context: dict[str, Any], snapshot: ContinuitySnapshot | None) -> dict[str, Any]:
        if snapshot is None or not is_active("V47_EXECUTION_CONTINUITY"):
            return compressed_context
        enriched = dict(compressed_context)
        enriched["execution_continuity"] = snapshot.to_compact_context()
        return enriched

    def postprocess_response(
        self,
        result: AnalyzeResponse,
        snapshot: ContinuitySnapshot | None,
    ) -> AnalyzeResponse:
        if snapshot is None or not is_active("V47_EXECUTION_CONTINUITY"):
            return result
        return apply_continuity_replanner(result, snapshot)


_engine = ExecutionContinuityEngine()


def observe_execution_continuity(
    *,
    session_id: str,
    task: str,
    page_context: Any,
    prior_steps: list[Any],
) -> ContinuitySnapshot | None:
    return _engine.observe(
        session_id=session_id,
        task=task,
        page_context=page_context,
        prior_steps=prior_steps,
    )


def enrich_planner_context(
    compressed_context: dict[str, Any],
    snapshot: ContinuitySnapshot | None,
) -> dict[str, Any]:
    return _engine.enrich_context(compressed_context, snapshot)


def postprocess_planner_response(
    result: AnalyzeResponse,
    snapshot: ContinuitySnapshot | None,
) -> AnalyzeResponse:
    return _engine.postprocess_response(result, snapshot)
