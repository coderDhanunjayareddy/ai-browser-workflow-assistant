"""M0 unit tests — criterion + failure-criterion evaluation."""
from benchmark.criteria import EvalContext, evaluate_success, evaluate_failure, all_passed
from benchmark.m0_models import (
    M0Criterion, M0CriterionKind as K, M0FailureCriterion, FailureCriterionKind as FK,
)


def ctx(**kw):
    base = dict(final_url="https://x/r?q=python", page_text="Python tutorial here",
                analysis_texts=["the price is rs 999"], steps_taken=3)
    base.update(kw)
    return EvalContext(**base)


def test_url_matches():
    r = evaluate_success([M0Criterion(K.url_matches, target=r"q=python")], ctx())
    assert r[0].passed


def test_url_matches_case_insensitive():
    r = evaluate_success([M0Criterion(K.url_matches, target=r"Q=PYTHON")], ctx())
    assert r[0].passed


def test_dom_text_present_absent():
    assert evaluate_success([M0Criterion(K.dom_text_present, target="tutorial")], ctx())[0].passed
    assert evaluate_success([M0Criterion(K.dom_text_absent, target="error")], ctx())[0].passed
    assert not evaluate_success([M0Criterion(K.dom_text_present, target="nope")], ctx())[0].passed


def test_extracted_value():
    assert evaluate_success([M0Criterion(K.extracted_value_present, target="price")], ctx())[0].passed
    assert evaluate_success([M0Criterion(K.extracted_value_matches, target=r"rs \d+")], ctx())[0].passed


def test_step_count_bounds():
    assert evaluate_success([M0Criterion(K.min_completed_steps, value=2)], ctx())[0].passed
    assert not evaluate_success([M0Criterion(K.min_completed_steps, value=9)], ctx())[0].passed
    assert evaluate_success([M0Criterion(K.step_count_in_range, value=5)], ctx())[0].passed
    assert not evaluate_success([M0Criterion(K.step_count_in_range, value=2)], ctx(steps_taken=4))[0].passed


def test_dom_element_present_uses_probe():
    c = ctx(element_present=lambda s: s == "#ok")
    assert evaluate_success([M0Criterion(K.dom_element_present, target="#ok")], c)[0].passed
    assert not evaluate_success([M0Criterion(K.dom_element_present, target="#no")], c)[0].passed


def test_all_passed_requires_nonempty():
    assert not all_passed([])
    assert all_passed(evaluate_success([M0Criterion(K.dom_text_present, target="Python")], ctx()))


def test_bad_regex_is_safe():
    r = evaluate_success([M0Criterion(K.url_matches, target="(")], ctx())
    assert not r[0].passed and "bad-regex" in r[0].observed


def test_failure_criteria():
    c = ctx(final_url="https://x/login", page_text="please log in", http_errors=["429"])
    assert evaluate_failure([M0FailureCriterion(FK.http_error, target="429")], c) is not None
    assert evaluate_failure([M0FailureCriterion(FK.url_matches_error, target=r"/login")], c) is not None
    assert evaluate_failure([M0FailureCriterion(FK.dom_error_present, target="log in")], c) is not None
    assert evaluate_failure([M0FailureCriterion(FK.dom_error_present, target="zzz")], c) is None
