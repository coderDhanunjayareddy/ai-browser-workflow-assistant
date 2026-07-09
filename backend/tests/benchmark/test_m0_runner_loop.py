"""M0 integration tests — the TaskRunner observe->analyze->gate->execute->validate loop.

Driven entirely by FakeDriver + FakeAnalyzeClient: no browser, no network, no AI.
"""
import tempfile

import pytest

from benchmark.m0_task_runner import TaskRunner
from benchmark.fakes import FakeDriver, FakeAnalyzeClient, page
from benchmark.m0_executor import ExecResult
from benchmark.analyze_client import ReportOutcomeDTO, ReplanOutcomeDTO
from benchmark.m0_models import (
    M0TaskDefinition, M0Criterion, M0CriterionKind as K, M0FailureCriterion,
    FailureCriterionKind as FK, Difficulty, BenchmarkCategory, TaskStatus, FailureCategory,
    HumanInterventionRules,
)


def task(**kw):
    d = dict(task_id="t", site_id="fixture_server", website="W", difficulty=Difficulty.simple,
             category=BenchmarkCategory.search, goal="g", start_url="http://x/a",
             max_steps=6, retry_budget=1)
    d.update(kw)
    return M0TaskDefinition(**d)


def runner(driver, client, mode="playwright", auto_approve=True):
    return TaskRunner(driver=driver, client=client, executor_mode=mode, run_id="t",
                      artifacts_dir=tempfile.gettempdir(), auto_approve=auto_approve)


class RecordingAnalyzeClient(FakeAnalyzeClient):
    def __init__(self, script: list, analysis: str = "") -> None:
        super().__init__(script, analysis=analysis)
        self.prior_steps_seen: list[list[dict]] = []

    def analyze(self, *, session_id: str, task: str, page_context: dict,
                prior_steps: list) :
        self.prior_steps_seen.append(list(prior_steps))
        return super().analyze(
            session_id=session_id,
            task=task,
            page_context=page_context,
            prior_steps=prior_steps,
        )


def test_happy_path_completes():
    d = FakeDriver([
        page("http://x/login", text="form", elements=[{"selector": "#u"}]),
        page("http://x/ok", text="Welcome tester"),
    ])
    c = FakeAnalyzeClient([("fill", "#u", "tester"), ("click", "#go", None)])
    t = task(success_criteria=[M0Criterion(K.dom_text_present, target="Welcome tester")])
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.completed
    assert r.ai_calls >= 1
    assert d.navigations and d.navigations[-1] == "http://x/a"


def test_navigation_only_completes_without_action():
    # criteria already satisfied at first observation -> 0 actions
    d = FakeDriver([page("http://x/nasa/", text="nasa profile")])
    c = FakeAnalyzeClient([])
    t = task(success_criteria=[M0Criterion(K.url_matches, target=r"/nasa/")])
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.completed
    assert r.steps_taken == 0


def test_grounding_failure_classified():
    d = FakeDriver([page("http://x/a", text="nothing")],
                   responder=lambda a, i: ExecResult(False, "not found", locator_strategy=None,
                                                      locator_attempts=5))
    c = FakeAnalyzeClient([("click", "button.x", None)] * 4)
    t = task(success_criteria=[M0Criterion(K.dom_text_present, target="done")], retry_budget=1)
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.failed
    assert r.failure_category == FailureCategory.grounding.value
    assert r.recoveries_attempted >= 1


def test_captcha_blocks():
    d = FakeDriver([page("http://x/a", text="x")], captcha=True)
    r = runner(d, FakeAnalyzeClient([("click", "#x", None)])).run(task())
    assert r.status == TaskStatus.blocked
    assert r.failure_category == FailureCategory.blocked_captcha.value
    assert not r.counts_toward_completion


def test_failure_criterion_trips():
    d = FakeDriver([page("http://x/login", text="please log in")])
    t = task(failure_criteria=[M0FailureCriterion(FK.dom_error_present, target="log in")],
             success_criteria=[M0Criterion(K.dom_text_present, target="never")])
    r = runner(d, FakeAnalyzeClient([])).run(t)
    assert r.status == TaskStatus.blocked  # login wall -> blocked category
    assert r.failure_category == FailureCategory.blocked_login_wall.value


def test_max_steps_timeout():
    # never satisfies; each action "succeeds" + changes page sig so it keeps looping
    pages = [page(f"http://x/{i}", text=f"page {i}", elements=[{"selector": "#x"}]) for i in range(10)]
    d = FakeDriver(pages)
    c = FakeAnalyzeClient([("click", "#x", None)] * 10)
    t = task(success_criteria=[M0Criterion(K.dom_text_present, target="unreachable")], max_steps=3)
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.timeout
    assert r.steps_taken == 3


def test_danger_action_requires_human_blocks_unattended():
    d = FakeDriver([page("http://x/a", text="x", elements=[{"selector": "#buy"}])])
    c = FakeAnalyzeClient([("click", "#buy", None)])
    # description carries a danger phrase -> classified danger -> require_human -> blocked
    c._script = [("click", "#buy", None)]
    t = task(goal="purchase",
             human_intervention_rules=HumanInterventionRules(danger_actions="require_human",
                                                             max_human_interventions=0),
             success_criteria=[M0Criterion(K.dom_text_present, target="done")])
    # monkeypatch the action description to include a danger phrase
    orig = c.analyze
    def patched(**kw):
        res = orig(**kw)
        if res.suggested_actions:
            res.suggested_actions[0].description = "pay now and place order"
        return res
    c.analyze = patched
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.blocked
    assert r.failure_category == "HUMAN_REQUIRED"


def test_rc1_successful_fills_with_no_signature_change_still_complete():
    """RC-1 regression: successful fills don't change the coarse DOM signature.

    Old behaviour treated each fill as 'no effect', consumed the single recovery, and
    failed EXECUTION before the final click. After the fix, recovery keys off executor
    failure only, so the task fills, fills, clicks, and completes.
    """
    def login_page():
        return page("http://127.0.0.1:5000/login", text="Login form here",
                    elements=[{"selector": "#u"}, {"selector": "#p"}, {"selector": "#go"}])
    # three identical-signature pages (the two fills change nothing observable), then success
    pages = [login_page(), login_page(), login_page(),
             page("http://127.0.0.1:5000/login", text="Welcome tester now",
                  elements=[{"selector": "#u"}, {"selector": "#p"}, {"selector": "#go"}])]
    d = FakeDriver(pages)
    c = FakeAnalyzeClient([("fill", "#u", "tester"), ("fill", "#p", "secret123"),
                           ("click", "#go", None)])
    t = task(retry_budget=1, max_steps=6,
             success_criteria=[M0Criterion(K.dom_text_present, target="Welcome tester")])
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.completed, f"{r.status} {r.failure_category} {r.failure_detail}"
    assert r.steps_taken == 3


# ── Planner Contract V2: outcome-kind dispatch ───────────────────────────────

def test_report_outcome_completes_when_claim_matches_real_criteria():
    # The Amazon-shaped case: the answer is already visible, no action needed.
    d = FakeDriver([page("http://x/product", text="price page")])
    c = FakeAnalyzeClient([
        {"outcome_kind": "report",
         "report": ReportOutcomeDTO(answer="₹15,299.00", claim="price already visible")},
    ])
    t = task(success_criteria=[M0Criterion(K.extracted_value_present, target="₹15,299.00")])
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.completed
    assert r.steps_taken == 1
    assert r.steps[0].action_type == "report"


def test_report_outcome_does_not_self_certify_when_criteria_still_fail():
    # Report is a claim, never self-certification: an unverified claim must NOT
    # complete the task — Validation (real success criteria) remains the authority.
    d = FakeDriver([page("http://x/product", text="price page")])
    c = FakeAnalyzeClient([
        {"outcome_kind": "report",
         "report": ReportOutcomeDTO(answer="wrong value", claim="I believe this is the price")},
    ])
    t = task(max_steps=2,
             success_criteria=[M0Criterion(K.extracted_value_present, target="₹99,999.00")])
    r = runner(d, c).run(t)
    assert r.status != TaskStatus.completed
    assert r.steps[0].action_type == "report"


def test_repeated_unsupported_reports_trigger_replan_breadcrumb():
    d = FakeDriver([page("http://x/product", text="search results")])
    c = RecordingAnalyzeClient([
        {"outcome_kind": "report",
         "report": ReportOutcomeDTO(answer="not enough", claim="price is available")},
        {"outcome_kind": "report",
         "report": ReportOutcomeDTO(answer="still not enough", claim="price is available")},
        ("click", "#product", None),
    ])
    t = task(max_steps=3,
             success_criteria=[M0Criterion(K.extracted_value_present, target="missing-price")])

    runner(d, c).run(t)

    assert any(
        step.get("action_type") == "replan"
        and "semantic progress" in step.get("execution_result", "")
        for step in c.prior_steps_seen[-1]
    )


def test_report_outcome_completes_with_semantic_page_evidence():
    pg = page("http://x/results", text="navigation shell",
              title="Python tutorial - Search results",
              elements=[{"selector": "#q", "text": "", "accessibility_name": "Search"}])
    pg["content_blocks"] = [{"text": "Python Full Course for Beginners"}]
    d = FakeDriver([pg])
    c = FakeAnalyzeClient([
        {"outcome_kind": "report",
         "report": ReportOutcomeDTO(answer="Python Full Course", claim="result is visible")},
    ])
    t = task(success_criteria=[
        M0Criterion(K.dom_text_present, target="Python tutorial"),
        M0Criterion(K.extracted_value_present, target="Python Full Course"),
    ])
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.completed
    assert r.steps[0].action_type == "report"


def test_replan_outcome_takes_no_action_then_next_turn_completes():
    d = FakeDriver([
        page("http://x/a", text="start", elements=[{"selector": "#x"}]),
        page("http://x/b", text="done now"),
    ])
    c = FakeAnalyzeClient([
        {"outcome_kind": "replan", "replan": ReplanOutcomeDTO(reason="wrong approach, try direct click")},
        ("click", "#x", None),
    ])
    t = task(success_criteria=[M0Criterion(K.dom_text_present, target="done now")])
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.completed
    assert r.steps_taken == 2
    assert r.steps[0].action_type == "replan"
    assert r.steps[0].action_selector is None  # no action was executed on the replan turn
    assert r.steps[1].action_type == "click"


def test_existing_act_only_scripts_are_unaffected_by_outcome_kind_default():
    # Backward compatibility: scripts/fakes that never set outcome_kind (the entire
    # existing test suite) must behave identically — outcome_kind defaults to "act".
    d = FakeDriver([
        page("http://x/login", text="form", elements=[{"selector": "#u"}]),
        page("http://x/ok", text="Welcome tester"),
    ])
    c = FakeAnalyzeClient([("fill", "#u", "tester"), ("click", "#go", None)])
    t = task(success_criteria=[M0Criterion(K.dom_text_present, target="Welcome tester")])
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.completed


def test_repeated_identical_actions_trigger_replan_breadcrumb():
    unchanged = page("http://x/search", text="same results", elements=[{"selector": "#next"}])
    d = FakeDriver([unchanged, unchanged, unchanged])
    c = RecordingAnalyzeClient([
        ("click", "#next", None),
        ("click", "#next", None),
        ("click", "#next", None),
    ])
    t = task(max_steps=3,
             success_criteria=[M0Criterion(K.dom_text_present, target="never appears")])

    runner(d, c).run(t)

    assert any(
        step.get("action_type") == "replan"
        and "semantic progress" in step.get("execution_result", "")
        for step in c.prior_steps_seen[-1]
    )


def test_semantic_progress_resets_convergence_in_runner():
    d = FakeDriver([
        page("http://x/search", text="page one", elements=[{"selector": "#next"}]),
        page("http://x/search", text="page two", elements=[{"selector": "#next"}]),
        page("http://x/search", text="page three", elements=[{"selector": "#next"}]),
    ])
    c = RecordingAnalyzeClient([
        ("click", "#next", None),
        ("click", "#next", None),
        ("click", "#next", None),
    ])
    t = task(max_steps=3,
             success_criteria=[M0Criterion(K.dom_text_present, target="never appears")])

    runner(d, c).run(t)

    assert not any(
        step.get("action_type") == "replan"
        for seen in c.prior_steps_seen
        for step in seen
    )


def test_recovery_breadcrumb_then_success():
    # step 1 fails (no effect, same page), recovery retries, step 2 succeeds + completes
    state = {"calls": 0}
    def responder(action, idx):
        state["calls"] += 1
        if state["calls"] == 1:
            return ExecResult(False, "no effect", locator_strategy="css_selector", locator_attempts=1)
        return ExecResult(True, "ok", locator_strategy="css_selector", locator_attempts=1)
    d = FakeDriver([
        page("http://x/a", text="start", elements=[{"selector": "#x"}]),
        page("http://x/b", text="done now"),
    ], responder=responder)
    c = FakeAnalyzeClient([("click", "#x", None), ("click", "#x", None)])
    t = task(success_criteria=[M0Criterion(K.dom_text_present, target="done now")], retry_budget=2)
    r = runner(d, c).run(t)
    assert r.status == TaskStatus.completed
    assert r.recoveries_attempted >= 1
