from __future__ import annotations

from app.benchmark.benchmark_service import BenchmarkService


class BenchmarkController:
    def __init__(self, service: BenchmarkService):
        self.service = service

    def catalog(self):
        return self.service.catalog()

    def benchmark(self, benchmark_id: str):
        return self.service.benchmark(benchmark_id)

    def run(self, run_id: str):
        return self.service.get_run(run_id)

    def report(self, run_id: str):
        return self.service.report(run_id)

    def failures(self, run_id: str):
        return self.service.failures(run_id)

    def metrics(self):
        return self.service.metrics()

    def history(self):
        return self.service.history()

    def trends(self):
        return self.service.trends()

    def export(self):
        return self.service.export()
