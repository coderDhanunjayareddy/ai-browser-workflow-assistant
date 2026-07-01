"""M0 unit tests — JSON / Markdown / HTML report generation + baseline delta."""
import json

from benchmark import m0_report
from benchmark.m0_models import M0TaskResult, M0StepRecord, TaskStatus, FailureCategory


def _results():
    ok = M0TaskResult(task_id="fixture__login_form", website="Fixture", difficulty="simple",
                      category="FORM_SUBMIT", executor_mode="playwright", status=TaskStatus.completed)
    ok.steps = [M0StepRecord(0, action_type="click", executed=True, execution_success=True,
                             validation_passed=True, ai_called=True, prompt_tokens=900,
                             completion_tokens=100, locator_strategy="css_selector")]
    fail = M0TaskResult(task_id="amazon_in__x", website="Amazon", difficulty="medium",
                        category="SEARCH", executor_mode="playwright", status=TaskStatus.failed)
    fail.failure_category = FailureCategory.execution.value
    fail.failure_detail = "no effect"
    blk = M0TaskResult(task_id="cross__x", website="X", difficulty="complex", category="CROSS_SITE",
                       executor_mode="playwright", status=TaskStatus.blocked, expect_failure=True)
    blk.failure_category = FailureCategory.blocked_captcha.value
    return [ok, fail, blk]


META = {"run_id": "r1", "suite": "smoke", "executor_mode": "playwright", "duration_s": 12}


def test_json_report_serializable_and_complete():
    rep = m0_report.build_report(meta=META, results=_results(), executor_mode="playwright")
    s = json.dumps(rep)  # must not raise
    assert '"completion_rate"' in s
    assert rep["summary"]["tasks_counted"] == 2  # blocked excluded
    assert rep["summary"]["completion_rate"] == 0.5
    assert len(rep["task_results"]) == 3


def test_markdown_sections():
    rep = m0_report.build_report(meta=META, results=_results(), executor_mode="playwright")
    md = m0_report.render_markdown(rep)
    assert "# M0 Benchmark Report" in md
    assert "Task Completion Rate" in md
    assert "Failure Distribution" in md
    assert "expected-failure" in md  # the blocked cross-site task is tagged


def test_html_is_self_contained():
    rep = m0_report.build_report(meta=META, results=_results(), executor_mode="playwright")
    html = m0_report.render_html(rep)
    assert "<style>" in html and "<script>" in html
    assert "src=\"http" not in html        # no external scripts
    assert "href=\"http" not in html       # no external stylesheets
    assert "window.__M0_REPORT__" in html  # embedded data
    assert "50%" in html or "0.5" in html


def test_baseline_delta():
    baseline = {"meta": {"run_id": "b"}, "summary": {"completion_rate": 0.70}}
    rep = m0_report.build_report(meta=META, results=_results(), executor_mode="playwright",
                                 baseline=baseline)
    assert abs(rep["summary"]["completion_rate_delta_from_baseline"] - (0.5 - 0.70)) < 1e-9
    assert rep["summary"]["baseline_run_id"] == "b"


def test_recommendations_point_at_dominant_failure():
    rep = m0_report.build_report(meta=META, results=_results(), executor_mode="playwright")
    joined = " ".join(rep["recommendations"])
    assert "EXECUTION" in joined or "Recovery" in joined
