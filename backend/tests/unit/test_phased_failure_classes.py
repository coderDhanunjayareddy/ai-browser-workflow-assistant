"""Phase D — Unit tests: failure_classes.py (Failure Classification Engine)."""
import pytest
from app.execution_gateway.browser import failure_classes as fc
from app.execution_gateway.browser.failure_classes import (
    FailureCategory, FailureSeverity, RecoveryAction, PROFILES,
    RETRYABLE_CATEGORIES, PERMANENT_CATEGORIES, profile_for, classify_failure, classify_category,
)


class TestEnums:
    def test_categories_count(self):
        assert len(FailureCategory) == 19   # +AmbiguousLocator (Phase F reliability fix)
    def test_required_categories_present(self):
        for name in ["ElementNotFound", "ElementHidden", "DetachedElement", "NavigationTimeout",
                     "PageCrash", "DownloadTimeout", "UploadFailure", "ValidationFailure",
                     "UnexpectedPopup", "NetworkIdleTimeout", "AuthenticationExpired"]:
            assert any(c.value == name for c in FailureCategory)
    def test_severity_values(self):
        assert FailureSeverity.transient.value == "TRANSIENT"
        assert FailureSeverity.recoverable.value == "RECOVERABLE"
        assert FailureSeverity.permanent.value == "PERMANENT"
    def test_recovery_actions(self):
        for a in ["WAIT", "SCROLL_INTO_VIEW", "REFRESH_LOCATOR", "REQUERY",
                  "WAIT_NETWORK_IDLE", "RELOAD_PAGE", "REREAD_PAGE", "DISMISS_POPUP", "NONE"]:
            assert any(r.value == a for r in RecoveryAction)


class TestProfiles:
    def test_every_category_has_profile(self):
        for c in FailureCategory:
            assert c in PROFILES
    def test_profile_has_fields(self):
        for c, p in PROFILES.items():
            assert isinstance(p.severity, FailureSeverity)
            assert isinstance(p.retryable, bool)
            assert isinstance(p.recommended_recovery, tuple)
    def test_retryable_permanent_disjoint(self):
        assert RETRYABLE_CATEGORIES.isdisjoint(PERMANENT_CATEGORIES)
    def test_permanent_categories(self):
        for c in [FailureCategory.upload_failure, FailureCategory.authentication_expired,
                  FailureCategory.invalid_selector, FailureCategory.navigation_failed,
                  FailureCategory.unknown]:
            assert c in PERMANENT_CATEGORIES
            assert profile_for(c).retryable is False
    def test_retryable_categories(self):
        for c in [FailureCategory.element_not_found, FailureCategory.element_hidden,
                  FailureCategory.detached_element, FailureCategory.navigation_timeout,
                  FailureCategory.page_crash, FailureCategory.validation_failure]:
            assert c in RETRYABLE_CATEGORIES
            assert profile_for(c).retryable is True
    def test_recovery_recommendations(self):
        assert RecoveryAction.scroll_into_view in profile_for(FailureCategory.element_hidden).recommended_recovery
        assert RecoveryAction.requery in profile_for(FailureCategory.detached_element).recommended_recovery
        assert RecoveryAction.wait_network_idle in profile_for(FailureCategory.navigation_timeout).recommended_recovery
        assert RecoveryAction.reread_page in profile_for(FailureCategory.validation_failure).recommended_recovery
        assert RecoveryAction.reload_page in profile_for(FailureCategory.page_crash).recommended_recovery
    def test_permanent_recovery_is_none(self):
        for c in PERMANENT_CATEGORIES:
            assert profile_for(c).recommended_recovery == (RecoveryAction.none,)
    def test_to_dict(self):
        d = profile_for(FailureCategory.element_hidden).to_dict()
        for k in ["category", "severity", "retryable", "recommended_recovery"]:
            assert k in d


class TestClassification:
    @pytest.mark.parametrize("msg,phase,expected", [
        ("no node found", "click", FailureCategory.element_not_found),
        ("waiting for selector", "click", FailureCategory.element_not_found),
        ("element is hidden / not visible", "click", FailureCategory.element_hidden),
        ("element intercepts pointer events", "click", FailureCategory.element_hidden),
        ("element is outside of the viewport", "click", FailureCategory.element_hidden),
        ("element is detached from the DOM", "click", FailureCategory.detached_element),
        ("stale element handle", "click", FailureCategory.stale_element),
        ("Timeout 30000ms exceeded", "navigate", FailureCategory.navigation_timeout),
        ("Timeout exceeded waiting for networkidle", "navigate", FailureCategory.network_idle_timeout),
        ("target closed", "click", FailureCategory.page_crash),
        ("page has been closed", "extract", FailureCategory.page_crash),
        ("unexpected popup appeared", "click", FailureCategory.unexpected_popup),
        ("a dialog opened", "click", FailureCategory.unexpected_popup),
        ("download timeout exceeded", "download", FailureCategory.download_timeout),
        ("download did not complete", "download", FailureCategory.download_failure),
        ("set_input_files failed", "upload", FailureCategory.upload_failure),
        ("is not a valid selector", "click", FailureCategory.invalid_selector),
        ("403 Forbidden unauthorized", "navigate", FailureCategory.authentication_expired),
        ("session expired, login required", "click", FailureCategory.authentication_expired),
        ("net::ERR_NAME_NOT_RESOLVED", "navigate", FailureCategory.navigation_failed),
        # Phase F — ambiguous locator (strict uniqueness / strict-mode violation, >1 match)
        ("strict uniqueness failed: text='Edit' matched 2 elements (not unique)", "click",
         FailureCategory.ambiguous_locator),
        ("strict mode violation: locator resolved to 3 elements", "click",
         FailureCategory.ambiguous_locator),
    ])
    def test_classify(self, msg, phase, expected):
        a = classify_failure(Exception(msg), phase=phase)
        assert a.category == expected
        assert a.profile.category == expected

    def test_ambiguous_locator_is_permanent(self):
        a = classify_failure(Exception("strict uniqueness failed: text='Edit' matched 2 elements"), phase="click")
        assert a.category == FailureCategory.ambiguous_locator
        assert a.profile.retryable is False
        assert a.profile.severity == FailureSeverity.permanent
        assert a.profile.recommended_recovery == (RecoveryAction.none,)

    def test_strict_zero_match_is_not_ambiguous(self):
        # a strict failure with 0 matches is genuinely missing (recoverable), NOT ambiguous
        a = classify_failure(Exception("strict uniqueness failed: id='x' matched 0 elements (no node found)"), phase="click")
        assert a.category == FailureCategory.element_not_found
        assert a.profile.retryable is True

    def test_analysis_to_dict(self):
        a = classify_failure(Exception("no node found"), phase="click")
        d = a.to_dict()
        for k in ["category", "profile", "base"]:
            assert k in d

    def test_classify_category_helper(self):
        assert classify_category(Exception("element is hidden"), phase="click") == FailureCategory.element_hidden

    def test_hidden_from_any_base(self):
        # even without an element_not_found base, "hidden" keyword wins
        assert classify_failure(Exception("totally weird but hidden text"), phase="x").category == FailureCategory.element_hidden

    def test_timeout_validation_phase(self):
        a = classify_failure(Exception("Timeout 5000ms exceeded"), phase="validate")
        # validate-phase timeout maps to a retryable category
        assert a.profile.retryable is True
