from __future__ import annotations

import time

from app.runtime_state_manager.models import RuntimeArtifact, RuntimeConsistencyResult, RuntimeRecoveryEvent, RuntimeTab, RuntimeTelemetry, RuntimeWindow


def build_runtime_telemetry(
    *,
    started_at: float,
    sync_ms: int,
    tabs: list[RuntimeTab],
    windows: list[RuntimeWindow],
    artifacts: list[RuntimeArtifact],
    consistency: RuntimeConsistencyResult,
    recovery: RuntimeRecoveryEvent,
    checkpoint_restored: bool = False,
) -> RuntimeTelemetry:
    return RuntimeTelemetry(
        registry_lookup_ms=int((time.perf_counter() - started_at) * 1000),
        synchronization_ms=sync_ms,
        tab_count=len(tabs),
        window_count=len(windows),
        artifact_count=len(artifacts),
        registry_repairs=1 if recovery.recovered and recovery.strategy != "none" else 0,
        recovery_events=0 if recovery.strategy == "none" else 1,
        consistency_violations=len(consistency.violations),
        checkpoint_restores=1 if checkpoint_restored else 0,
    )
