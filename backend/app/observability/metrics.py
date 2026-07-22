from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MetricPoint:
    name: str
    value: float
    run_id: str
    tags: dict[str, str]


class InMemoryMetricSink:
    def __init__(self, max_points: int = 1000):
        self.max_points = max(1, max_points)
        self.points: list[MetricPoint] = []

    def record(self, name: str, value: float, *, run_id: str, tags: dict[str, str] | None = None) -> None:
        self.points.append(MetricPoint(name=name, value=value, run_id=run_id, tags=tags or {}))
        if len(self.points) > self.max_points:
            self.points = self.points[-self.max_points:]

    def snapshot(self) -> list[MetricPoint]:
        return list(self.points)


default_metric_sink = InMemoryMetricSink()
