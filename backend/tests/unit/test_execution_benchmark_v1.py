from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.benchmark.benchmark_catalog import benchmark_catalog, get_benchmark
from app.benchmark.benchmark_diagnostics import FailureClassifier
from app.benchmark.benchmark_executor import BenchmarkExecutor
from app.benchmark.benchmark_metrics import compute_metrics
from app.benchmark.benchmark_repository import SqlAlchemyBenchmarkRepository
from app.benchmark.benchmark_runner import BenchmarkRunner
from app.benchmark.benchmark_service import BenchmarkService
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app as fastapi_app
from app.models.db import (
    BenchmarkExecutionTraceRecord,
    BenchmarkFailureRecord,
    BenchmarkMetricRecord,
    BenchmarkReportRecord,
    BenchmarkRunRecord,
    MissionIntentRecord,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    monkeypatch.setattr(settings, "execution_benchmark_v1", "shadow")


def _snapshots(benchmark_id: str = "exec_research"):
    benchmark = get_benchmark(benchmark_id)
    return {
        "mission_blueprint": {"expected_nodes": benchmark.expected_blueprint, "observed_nodes": benchmark.expected_blueprint},
        "ledger_intents": [
            {"intent_id": f"i{index}", "blueprint_node_id": node, "status": "COMPLETED"}
            for index, node in enumerate(benchmark.expected_blueprint)
        ],
        "provider_execution": [{"provider": provider, "latency_ms": 25} for provider in benchmark.expected_providers],
        "browser_actions": [{"action_type": "navigate"}],
        "evidence": [{"evidence_type": "field", "confidence": 0.9} for _ in benchmark.expected_blueprint],
        "validation": [{"passed": True}],
        "mission_completion": {"complete": True, "reason": "criteria_satisfied"},
        "decision_comparison": [{"runtime_decision": "CONTINUE", "cognitive_decision": "CONTINUE", "agreement": "exact", "confidence": 0.9}],
        "duration": {"duration_ms": 1200},
        "planner_calls": {"count": 1},
        "timeline": [{"order": 1, "stage": "captured"}],
    }


def test_catalog_contains_execution_benchmark_categories():
    catalog = benchmark_catalog()
    categories = {item.category for item in catalog}

    assert len(catalog) == 14
    assert {"research", "shopping", "forms", "navigation", "extraction", "authentication", "upload", "download", "dashboard", "cross_system"} <= categories


def test_runner_captures_trace_metrics_reports_and_score():
    benchmark = get_benchmark("exec_research")
    result = BenchmarkRunner().run(benchmark=benchmark, mission_id="mission1", snapshots=_snapshots())

    assert result.status == "captured"
    assert result.score > 0.9
    assert result.metrics["mission_success_rate"] == 1.0
    assert result.trace.stages["mission_completion"]["complete"] is True
    assert result.reports[0].json_report["regression_report"]["runtime_v1_unchanged"] is True
    assert "Runtime impact" in result.reports[0].markdown_report


def test_metric_computation_and_failure_classification():
    benchmark = get_benchmark("exec_forms")
    trace = BenchmarkRunner().run(
        benchmark=benchmark,
        snapshots={
            "mission_blueprint": {"expected_nodes": benchmark.expected_blueprint, "observed_nodes": []},
            "ledger_intents": [],
            "mission_completion": {"complete": False},
        },
    ).trace
    metrics = compute_metrics(benchmark=benchmark, trace=trace)
    failures = FailureClassifier().classify(trace, metrics)

    assert metrics["blueprint_accuracy"] == 0.0
    assert failures
    assert failures[0].affected_subsystem in {"Blueprint", "Unknown"}


def test_repository_stores_all_additive_benchmark_tables(db_session):
    result = BenchmarkRunner().run(benchmark=get_benchmark("exec_navigation"), mission_id="m-nav", snapshots=_snapshots("exec_navigation"))
    saved = SqlAlchemyBenchmarkRepository(db_session).save(result)
    loaded = SqlAlchemyBenchmarkRepository(db_session).get_run(saved.run_id)

    assert loaded is not None
    assert db_session.query(BenchmarkRunRecord).count() == 1
    assert db_session.query(BenchmarkExecutionTraceRecord).count() == 1
    assert db_session.query(BenchmarkMetricRecord).count() == 1
    assert db_session.query(BenchmarkReportRecord).count() == 1
    assert db_session.query(BenchmarkFailureRecord).count() == 0
    assert db_session.query(MissionIntentRecord).count() == 0


def test_service_history_metrics_trends_export_and_descriptor(db_session):
    service = BenchmarkService(SqlAlchemyBenchmarkRepository(db_session))
    captured = service.capture_run("exec_research", mission_id="m1", snapshots=_snapshots())
    descriptor = service.launch_descriptor("exec_research")

    assert captured is not None
    assert descriptor["harness_behavior"] == "observe_only"
    assert service.metrics()["run_count"] == 1
    assert service.history()[0]["benchmark_id"] == "exec_research"
    assert service.trends()["run_count"] == 1
    assert service.export()["run_count"] == 1


def test_api_endpoints_are_read_only_and_feature_flagged(db_session, monkeypatch):
    service = BenchmarkService(SqlAlchemyBenchmarkRepository(db_session))
    run = service.capture_run("exec_research", mission_id="api-mission", snapshots=_snapshots())

    def override_db():
        yield db_session

    fastapi_app.dependency_overrides[get_db] = override_db
    try:
        client = TestClient(fastapi_app)
        paths = [
            "/benchmarks",
            "/benchmarks/catalog",
            f"/benchmarks/run/{run.run_id}",
            f"/benchmarks/report/{run.run_id}",
            f"/benchmarks/failures/{run.run_id}",
            "/benchmarks/metrics",
            "/benchmarks/history",
            "/benchmarks/trends",
            "/benchmarks/export",
        ]
        responses = [client.get(path) for path in paths]
        monkeypatch.setattr(settings, "execution_benchmark_v1", "off")
        disabled = client.get("/benchmarks")
    finally:
        fastapi_app.dependency_overrides.clear()

    assert all(response.status_code == 200 for response in responses)
    assert responses[0].json()["benchmarks"][0]["id"].startswith("exec_")
    assert responses[2].json()["run_id"] == run.run_id
    assert responses[5].json()["metrics"]["run_count"] == 1
    assert disabled.status_code == 404
    assert db_session.query(MissionIntentRecord).count() == 0


def test_runtime_v1_isolation_no_mission_intents_created(db_session):
    before = db_session.query(MissionIntentRecord).count()
    BenchmarkService(SqlAlchemyBenchmarkRepository(db_session)).capture_run("exec_research", snapshots=_snapshots())
    after = db_session.query(MissionIntentRecord).count()

    assert before == after == 0
