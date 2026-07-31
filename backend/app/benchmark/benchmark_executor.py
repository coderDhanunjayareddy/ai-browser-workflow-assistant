from __future__ import annotations

from app.benchmark.benchmark_models import BenchmarkMission


class BenchmarkExecutor:
    """Observational mission launcher descriptor.

    This class never calls Runtime V1. It returns the launch payload a human or
    external harness can use to run the mission through the normal product path.
    """

    def launch_descriptor(self, benchmark: BenchmarkMission) -> dict:
        return {
            "benchmark_id": benchmark.id,
            "user_prompt": benchmark.user_prompt,
            "timeout": benchmark.timeout,
            "expected_providers": benchmark.expected_providers,
            "execution_owner": "runtime_v1",
            "harness_behavior": "observe_only",
        }
