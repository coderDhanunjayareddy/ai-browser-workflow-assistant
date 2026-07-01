"""M0 unit tests — domain models + derived metrics."""
from benchmark.m0_models import (
    M0TaskResult, M0StepRecord, TaskStatus, Difficulty, BenchmarkCategory,
    M0Criterion, M0CriterionKind, FailureCategory, BLOCKED_CATEGORIES,
)


def _result(status=TaskStatus.completed):
    r = M0TaskResult(task_id="t", website="w", difficulty="simple", category="SEARCH",
                     executor_mode="playwright", status=status)
    return r


def test_derived_step_counts():
    r = _result()
    r.steps = [
        M0StepRecord(0, action_type="click", executed=True, execution_success=True,
                     validation_passed=True, ai_called=True, prompt_tokens=100, completion_tokens=20,
                     locator_strategy="css_selector"),
        M0StepRecord(1, action_type="fill", executed=True, execution_success=False,
                     validation_passed=False, ai_called=True, is_recovery=True),
        M0StepRecord(2, action_type="click", executed=True, execution_success=True,
                     validation_passed=True, human_intervention=True,
                     locator_strategy="data_testid", is_recovery=True, recovery_success=True),
    ]
    assert r.steps_taken == 3
    assert r.steps_successful == 2
    assert r.steps_failed == 1
    assert r.human_interventions == 1
    assert r.recoveries_attempted == 2
    assert r.recoveries_successful == 1
    assert r.validations_passed == 2
    assert r.validations_failed == 1
    assert r.ai_calls == 2
    assert r.total_tokens == 120
    assert r.locator_strategy_counts == {"css_selector": 1, "data_testid": 1}


def test_blocked_and_skipped_excluded_from_completion():
    assert _result(TaskStatus.completed).counts_toward_completion is True
    assert _result(TaskStatus.failed).counts_toward_completion is True
    assert _result(TaskStatus.blocked).counts_toward_completion is False
    assert _result(TaskStatus.skipped).counts_toward_completion is False


def test_blocked_categories_membership():
    assert FailureCategory.blocked_captcha in BLOCKED_CATEGORIES
    assert FailureCategory.grounding not in BLOCKED_CATEGORIES


def test_to_dict_roundtrip_shape():
    r = _result()
    r.steps = [M0StepRecord(0, action_type="click", executed=True, execution_success=True)]
    d = r.to_dict()
    assert d["status"] == "COMPLETED"
    assert d["steps_taken"] == 1
    assert isinstance(d["steps"], list) and d["steps"][0]["action_type"] == "click"
