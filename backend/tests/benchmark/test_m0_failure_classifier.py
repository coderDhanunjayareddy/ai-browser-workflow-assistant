"""M0 unit tests — failure classifier decision tree (one failure -> one category)."""
import pytest

from benchmark.failure_classifier import FailureSignal, classify
from benchmark.m0_models import FailureCategory as FC


@pytest.mark.parametrize("sig,expected", [
    (FailureSignal(error_type="TimeoutError"), FC.infrastructure),
    (FailureSignal(http_status=500), FC.infrastructure),
    (FailureSignal(page_text="complete the CAPTCHA please"), FC.blocked_captcha),
    (FailureSignal(http_status=429), FC.blocked_rate_limit),
    (FailureSignal(http_status=403), FC.blocked_anti_bot),
    (FailureSignal(page_text="unusual traffic from your network"), FC.blocked_anti_bot),
    (FailureSignal(page_text="Log in to continue"), FC.blocked_login_wall),
    (FailureSignal(final_url="https://accounts.google.com/x"), FC.blocked_auth_expired),
    (FailureSignal(needs_visual=True), FC.vision_required),
    (FailureSignal(locator_all_failed=True), FC.grounding),
    (FailureSignal(locator_all_failed=True, element_visible_pixels=True, element_in_dom=False),
     FC.perception),
    (FailureSignal(executed=True, dom_changed=False), FC.execution),
    (FailureSignal(executed=True, dom_changed=True, phase="validate"), FC.validation),
    (FailureSignal(recovery_attempted=True), FC.recovery),
    (FailureSignal(timed_out=True), FC.timeout),
    (FailureSignal(is_cross_site=True), FC.orchestration),
    (FailureSignal(), FC.unknown),
])
def test_classification(sig, expected):
    assert classify(sig) == expected


def test_priority_block_over_grounding():
    # a captcha page where the locator also failed is still BLOCKED, not GROUNDING
    sig = FailureSignal(page_text="CAPTCHA", locator_all_failed=True)
    assert classify(sig) == FC.blocked_captcha


def test_infra_beats_everything():
    sig = FailureSignal(error_type="ConnectionError", page_text="CAPTCHA", locator_all_failed=True)
    assert classify(sig) == FC.infrastructure


def test_rc2_local_login_url_is_not_auth_expired():
    """RC-2 regression: a local fixture URL containing '/login' must NOT be read as an
    expired auth session. A real remote auth redirect still is."""
    local = FailureSignal(final_url="http://127.0.0.1:5051/login", executed=True, dom_changed=False)
    assert classify(local) == FC.execution          # falls through to the real cause
    localhost = FailureSignal(final_url="http://localhost:8000/signin", executed=True, dom_changed=False)
    assert classify(localhost) == FC.execution
    remote = FailureSignal(final_url="https://www.linkedin.com/login", executed=True, dom_changed=False)
    assert classify(remote) == FC.blocked_auth_expired
