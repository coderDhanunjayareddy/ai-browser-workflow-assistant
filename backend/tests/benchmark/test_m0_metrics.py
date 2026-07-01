"""M0 unit tests — metrics aggregation, Wilson CI, cost, executor gap."""
from benchmark import m0_metrics
from benchmark.m0_models import (
    M0TaskResult, M0StepRecord, TaskStatus, FailureCategory,
)


def _task(status, difficulty="simple", category="SEARCH", site="s", failure=None, steps=3,
          exec_ok=True, val=True, tokens=(1000, 200), strat="css_selector"):
    r = M0TaskResult(task_id=f"t-{id(object())}", website=site, difficulty=difficulty,
                     category=category, executor_mode="playwright", status=status)
    for i in range(steps):
        r.steps.append(M0StepRecord(i, action_type="click", executed=True,
                                    execution_success=exec_ok, validation_passed=val,
                                    ai_called=True, prompt_tokens=tokens[0],
                                    completion_tokens=tokens[1], locator_strategy=strat,
                                    is_recovery=(i == 1), recovery_success=(i == 1 and exec_ok)))
    if failure:
        r.failure_category = failure.value
    r.duration_ms = 5000
    return r


def test_completion_rate_excludes_blocked_and_skipped():
    results = [
        _task(TaskStatus.completed),
        _task(TaskStatus.failed, failure=FailureCategory.grounding),
        _task(TaskStatus.blocked, failure=FailureCategory.blocked_captcha),
        _task(TaskStatus.skipped),
    ]
    agg = m0_metrics.aggregate(results, executor_mode="playwright")
    # counted = completed + failed = 2; completed = 1
    assert agg["summary"]["tasks_counted"] == 2
    assert agg["summary"]["completion_rate"] == 0.5


def test_wilson_interval_properties():
    assert m0_metrics.wilson_interval(0, 0) == (0.0, 0.0)
    lo, hi = m0_metrics.wilson_interval(5, 10)
    assert 0.0 < lo < 0.5 < hi < 1.0
    lo2, hi2 = m0_metrics.wilson_interval(10, 10)
    assert hi2 == 1.0


def test_cost_estimate_scales():
    c1 = m0_metrics.estimate_cost_usd(1_000_000, 0)
    c2 = m0_metrics.estimate_cost_usd(0, 1_000_000)
    assert c1 > 0 and c2 > c1  # completion priced higher than prompt


def test_by_difficulty_and_failure_distribution():
    results = [
        _task(TaskStatus.completed, difficulty="simple"),
        _task(TaskStatus.failed, difficulty="medium", failure=FailureCategory.execution),
        _task(TaskStatus.failed, difficulty="complex", failure=FailureCategory.execution),
    ]
    agg = m0_metrics.aggregate(results, executor_mode="playwright")
    assert agg["by_difficulty"]["simple"]["completion_rate"] == 1.0
    assert agg["by_difficulty"]["complex"]["completion_rate"] == 0.0
    assert agg["failure_distribution"]["EXECUTION"] == 2
    assert agg["locator_strategies"]["css_selector"] == 9


def test_executor_gap():
    pw = m0_metrics.aggregate([_task(TaskStatus.completed)], executor_mode="playwright")
    syn = m0_metrics.aggregate([_task(TaskStatus.failed, failure=FailureCategory.execution)],
                               executor_mode="synthetic")
    gap = m0_metrics.executor_gap(pw, syn)
    assert gap["overall"]["gap"] == 1.0  # pw 100% - syn 0%
