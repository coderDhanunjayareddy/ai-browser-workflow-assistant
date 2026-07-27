from __future__ import annotations

import time
from typing import Any

from app.feature_flags import is_active, is_shadow_or_active
from app.runtime_state_manager.artifacts import build_runtime_artifacts
from app.runtime_state_manager.checkpoints import RuntimeCheckpointStore, build_checkpoint
from app.runtime_state_manager.completion import artifact_completion_status
from app.runtime_state_manager.consistency import validate_runtime_consistency
from app.runtime_state_manager.logical_resources import build_logical_resources
from app.runtime_state_manager.models import RuntimeStateSnapshot
from app.runtime_state_manager.recovery import recover_runtime_state
from app.runtime_state_manager.registry import BrowserRuntimeRegistry
from app.runtime_state_manager.replay import runtime_replay_frames
from app.runtime_state_manager.sync import synchronize_runtime
from app.runtime_state_manager.telemetry import build_runtime_telemetry
from app.schemas.response import AnalyzeResponse, ReplanOutcome


class RuntimeStateManager:
    def __init__(self) -> None:
        self.registry = BrowserRuntimeRegistry()
        self.checkpoints = RuntimeCheckpointStore()

    def observe(
        self,
        *,
        session_id: str,
        page_context: Any,
        prior_steps: list[Any],
        current_phase: str | None = None,
        planner_response: AnalyzeResponse | None = None,
    ) -> RuntimeStateSnapshot | None:
        if not is_shadow_or_active("V49_RUNTIME_STATE_MANAGER"):
            return None
        started = time.perf_counter()
        windows, tabs, sync_ms = synchronize_runtime(
            self.registry,
            session_id=session_id,
            page_context=page_context,
            prior_steps=prior_steps,
        ) if is_shadow_or_active("V49_RUNTIME_SYNC") else ([], [], 0)
        artifacts = build_runtime_artifacts(page_context, prior_steps) if is_shadow_or_active("V49_ARTIFACT_ENGINE") else []
        focused_tab_id = next((tab.logical_id for tab in tabs if tab.active), None)
        consistency = validate_runtime_consistency(tabs=tabs, focused_tab_id=focused_tab_id, planner_response=planner_response)
        recovery = recover_runtime_state(consistency, tabs)
        checkpoint = build_checkpoint(
            session_id=session_id,
            current_phase=current_phase,
            tabs=tabs,
            artifacts=artifacts,
            recovery_state=recovery.strategy,
        )
        if is_shadow_or_active("V49_RUNTIME_CHECKPOINTS"):
            self.checkpoints.save(session_id, checkpoint)
        logical_resources = build_logical_resources(session_id=session_id, tabs=tabs, windows=windows, artifacts=artifacts)
        telemetry = build_runtime_telemetry(
            started_at=started,
            sync_ms=sync_ms,
            tabs=tabs,
            windows=windows,
            artifacts=artifacts,
            consistency=consistency,
            recovery=recovery,
        )
        from dataclasses import replace
        from app.runtime_state_manager.entity_pipeline_trace import entity_pipeline_telemetry

        telemetry = replace(telemetry, entity_pipeline=entity_pipeline_telemetry(session_id))
        replay = runtime_replay_frames(tabs, artifacts, checkpoint, session_id=session_id)
        return RuntimeStateSnapshot(
            schema_version="runtime_state_manager.v1",
            session_id=session_id,
            windows=windows,
            tabs=tabs,
            focused_tab_id=focused_tab_id,
            logical_resources=logical_resources,
            artifacts=artifacts,
            checkpoint=checkpoint,
            consistency=consistency,
            recovery=recovery,
            telemetry=telemetry,
            replay=replay,
        )

    def enrich_context(self, compressed_context: dict[str, Any], snapshot: RuntimeStateSnapshot | None) -> dict[str, Any]:
        if snapshot is None or not is_active("V49_RUNTIME_STATE_MANAGER"):
            return compressed_context
        enriched = dict(compressed_context)
        enriched["runtime_state_manager"] = snapshot.to_compact_context()
        return enriched

    def postprocess_response(
        self,
        result: AnalyzeResponse,
        snapshot: RuntimeStateSnapshot | None,
    ) -> AnalyzeResponse:
        if snapshot is None or not is_active("V49_RUNTIME_STATE_MANAGER"):
            return result
        if snapshot.consistency.valid:
            return result
        return AnalyzeResponse(
            session_id=result.session_id,
            analysis=f"{result.analysis}\n\nV4.9 Runtime State Manager rejected stale runtime state before execution.",
            outcome_kind="replan",
            clarification_question=None,
            report=None,
            replan=ReplanOutcome(
                reason=(
                    f"Runtime consistency violation: {snapshot.consistency.reason}. "
                    f"Recovery strategy: {snapshot.recovery.strategy}."
                )
            ),
            suggested_actions=[],
        )

    def phase_completion_evidence(self, snapshot: RuntimeStateSnapshot | None, phase: str, required_count: int = 1) -> dict[str, object]:
        if snapshot is None:
            return {"phase": phase, "complete": False, "required_count": required_count, "complete_count": 0, "artifact_ids": []}
        return artifact_completion_status(phase, snapshot.artifacts, required_count)

    def resolve_logical_tab_url(self, session_id: str, logical_tab_id: str) -> str | None:
        tab = self.registry.get_tab(session_id, logical_tab_id)
        if tab and tab.url.startswith(("http://", "https://")):
            return tab.url
        return None


_manager = RuntimeStateManager()


def observe_runtime_state(
    *,
    session_id: str,
    page_context: Any,
    prior_steps: list[Any],
    current_phase: str | None = None,
    planner_response: AnalyzeResponse | None = None,
) -> RuntimeStateSnapshot | None:
    return _manager.observe(
        session_id=session_id,
        page_context=page_context,
        prior_steps=prior_steps,
        current_phase=current_phase,
        planner_response=planner_response,
    )


def enrich_planner_context_with_runtime_state(compressed_context: dict[str, Any], snapshot: RuntimeStateSnapshot | None) -> dict[str, Any]:
    return _manager.enrich_context(compressed_context, snapshot)


def postprocess_with_runtime_state(result: AnalyzeResponse, snapshot: RuntimeStateSnapshot | None) -> AnalyzeResponse:
    return _manager.postprocess_response(result, snapshot)


def runtime_phase_completion(snapshot: RuntimeStateSnapshot | None, phase: str, required_count: int = 1) -> dict[str, object]:
    return _manager.phase_completion_evidence(snapshot, phase, required_count)


def resolve_logical_tab_url(session_id: str, logical_tab_id: str) -> str | None:
    return _manager.resolve_logical_tab_url(session_id, logical_tab_id)
