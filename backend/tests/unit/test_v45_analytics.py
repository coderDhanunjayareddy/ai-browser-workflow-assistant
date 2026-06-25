"""
V4.5 Unit Tests — Task Analytics.

Tests cover:
  - get_analytics() returns correct structure
  - record_task_created() increments total_tasks
  - record_task_completed() increments completed_tasks, updates duration
  - record_task_abandoned() increments abandoned_tasks
  - record_task_failed() increments failed_tasks
  - record_research_to_workflow() increments counter
  - record_approval_requested/resolved updates approval_rate
  - record_workflow_completion() increments counter
  - record_state_transition() builds histogram
  - thread safety via concurrent calls
"""
import pytest
import threading

import app.unified.analytics as analytics


@pytest.fixture(autouse=True)
def reset_analytics():
    analytics._reset_for_testing()
    yield
    analytics._reset_for_testing()


class TestGetAnalytics:
    def test_returns_dict(self):
        r = analytics.get_analytics()
        assert isinstance(r, dict)

    def test_all_required_keys_present(self):
        r = analytics.get_analytics()
        required = [
            "total_tasks", "active_tasks", "completed_tasks", "abandoned_tasks",
            "research_to_workflow_conversion", "approval_rate",
            "average_task_duration_ms", "workflow_completion_rate",
        ]
        for key in required:
            assert key in r, f"Missing key: {key}"

    def test_initial_values_are_zero(self):
        r = analytics.get_analytics()
        assert r["total_tasks"] == 0
        assert r["completed_tasks"] == 0


class TestTaskCreated:
    def test_increments_total(self):
        analytics.record_task_created()
        assert analytics.get_analytics()["total_tasks"] == 1

    def test_increments_active(self):
        analytics.record_task_created()
        assert analytics.get_analytics()["active_tasks"] == 1

    def test_multiple_increments(self):
        for _ in range(5):
            analytics.record_task_created()
        assert analytics.get_analytics()["total_tasks"] == 5


class TestTaskCompleted:
    def test_increments_completed(self):
        analytics.record_task_created()
        analytics.record_task_completed(duration_ms=500)
        r = analytics.get_analytics()
        assert r["completed_tasks"] == 1

    def test_decrements_active(self):
        analytics.record_task_created()
        analytics.record_task_completed(duration_ms=100)
        r = analytics.get_analytics()
        assert r["active_tasks"] == 0

    def test_updates_average_duration(self):
        analytics.record_task_created()
        analytics.record_task_completed(duration_ms=200)
        r = analytics.get_analytics()
        assert r["average_task_duration_ms"] == 200.0

    def test_average_across_multiple(self):
        for i in range(3):
            analytics.record_task_created()
            analytics.record_task_completed(duration_ms=(i + 1) * 100)
        r = analytics.get_analytics()
        assert r["average_task_duration_ms"] == pytest.approx(200.0, rel=0.01)


class TestTaskAbandoned:
    def test_increments_abandoned(self):
        analytics.record_task_created()
        analytics.record_task_abandoned()
        assert analytics.get_analytics()["abandoned_tasks"] == 1

    def test_decrements_active(self):
        analytics.record_task_created()
        analytics.record_task_abandoned()
        assert analytics.get_analytics()["active_tasks"] == 0


class TestTaskFailed:
    def test_increments_failed(self):
        analytics.record_task_created()
        analytics.record_task_failed()
        assert analytics.get_analytics()["failed_tasks"] == 1


class TestResearchToWorkflow:
    def test_increments_conversion_count(self):
        analytics.record_research_to_workflow()
        analytics.record_research_to_workflow()
        assert analytics.get_analytics()["research_to_workflow_conversion"] == 2


class TestApprovalAnalytics:
    def test_approval_rate_all_approved(self):
        analytics.record_approval_requested()
        analytics.record_approval_requested()
        analytics.record_approval_resolved(approved=True)
        analytics.record_approval_resolved(approved=True)
        r = analytics.get_analytics()
        assert r["approval_rate"] == pytest.approx(1.0, rel=0.01)

    def test_approval_rate_half_approved(self):
        analytics.record_approval_requested()
        analytics.record_approval_requested()
        analytics.record_approval_resolved(approved=True)
        analytics.record_approval_resolved(approved=False)
        r = analytics.get_analytics()
        assert r["approval_rate"] == pytest.approx(0.5, rel=0.01)

    def test_zero_approvals_rate_is_zero(self):
        r = analytics.get_analytics()
        assert r["approval_rate"] == 0.0


class TestWorkflowCompletion:
    def test_increments_workflow_completions(self):
        analytics.record_workflow_completion()
        analytics.record_workflow_completion()
        r = analytics.get_analytics()
        assert r["workflow_completions"] == 2


class TestStateTransition:
    def test_records_state_transitions(self):
        analytics.record_state_transition("CREATED", "RESEARCHING")
        analytics.record_state_transition("RESEARCHING", "RESEARCH_COMPLETE")
        r = analytics.get_analytics()
        hist = r.get("state_transitions", {})
        assert "CREATED->RESEARCHING" in hist
        assert hist["CREATED->RESEARCHING"] == 1


class TestThreadSafety:
    def test_concurrent_increments(self):
        errors = []
        def worker():
            try:
                analytics.record_task_created()
                analytics.record_task_completed(duration_ms=50)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []
        r = analytics.get_analytics()
        assert r["total_tasks"] == 50
        assert r["completed_tasks"] == 50
