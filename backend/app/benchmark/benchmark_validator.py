from __future__ import annotations

from app.benchmark.benchmark_models import BenchmarkMission, ExecutionTrace


class BenchmarkValidator:
    def validate(self, *, benchmark: BenchmarkMission, trace: ExecutionTrace) -> dict:
        blueprint = dict(trace.stages.get("mission_blueprint") or {})
        observed_nodes = set(blueprint.get("observed_nodes") or [])
        missing_nodes = [node for node in benchmark.expected_blueprint if node not in observed_nodes]
        providers = {str(item.get("provider")) for item in (trace.stages.get("provider_execution") or []) if isinstance(item, dict)}
        missing_providers = [provider for provider in benchmark.expected_providers if provider not in providers]
        return {
            "valid": not missing_nodes,
            "missing_blueprint_nodes": missing_nodes,
            "missing_providers": missing_providers,
            "execution_impact": "none",
        }
