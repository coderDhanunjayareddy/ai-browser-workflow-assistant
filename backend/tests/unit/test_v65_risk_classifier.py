"""
V6.5 Unit Tests — RiskClassifier (22 tests).
"""
import pytest
from app.trust.risk_classifier import RiskClassifier, classify, classify_many
from app.trust.models import RiskLevel


@pytest.fixture
def clf():
    return RiskClassifier()


class TestExactMatch:
    def test_read_page_low(self, clf):
        assert clf.classify("read_page") == RiskLevel.low

    def test_navigate_low(self, clf):
        assert clf.classify("navigate") == RiskLevel.low

    def test_research_low(self, clf):
        assert clf.classify("research") == RiskLevel.low

    def test_compare_low(self, clf):
        assert clf.classify("compare") == RiskLevel.low

    def test_scroll_low(self, clf):
        assert clf.classify("scroll") == RiskLevel.low

    def test_click_medium(self, clf):
        assert clf.classify("click") == RiskLevel.medium

    def test_form_fill_medium(self, clf):
        assert clf.classify("form_fill") == RiskLevel.medium

    def test_workflow_prepare_medium(self, clf):
        assert clf.classify("workflow_prepare") == RiskLevel.medium

    def test_message_send_high(self, clf):
        assert clf.classify("message_send") == RiskLevel.high

    def test_email_send_high(self, clf):
        assert clf.classify("email_send") == RiskLevel.high

    def test_share_high(self, clf):
        assert clf.classify("share") == RiskLevel.high

    def test_purchase_critical(self, clf):
        assert clf.classify("purchase") == RiskLevel.critical

    def test_delete_critical(self, clf):
        assert clf.classify("delete") == RiskLevel.critical

    def test_payment_critical(self, clf):
        assert clf.classify("payment") == RiskLevel.critical

    def test_checkout_critical(self, clf):
        assert clf.classify("checkout") == RiskLevel.critical

    def test_send_money_critical(self, clf):
        assert clf.classify("send_money") == RiskLevel.critical


class TestCaseInsensitivity:
    def test_uppercase_normalized(self, clf):
        assert clf.classify("PURCHASE") == RiskLevel.critical

    def test_mixed_case(self, clf):
        assert clf.classify("Delete") == RiskLevel.critical

    def test_with_whitespace(self, clf):
        assert clf.classify("  click  ") == RiskLevel.medium


class TestSubstringFallback:
    def test_unknown_with_purchase_substring(self, clf):
        assert clf.classify("confirm_purchase_now") == RiskLevel.critical

    def test_unknown_with_send_substring(self, clf):
        assert clf.classify("quick_send_action") == RiskLevel.high

    def test_unknown_with_read_substring(self, clf):
        assert clf.classify("background_read_action") == RiskLevel.low


class TestUnknownDefault:
    def test_unknown_action_defaults_to_medium(self, clf):
        assert clf.classify("totally_unknown_action_xyz") == RiskLevel.medium


class TestClassifyMany:
    def test_highest_wins(self, clf):
        assert clf.classify_many(["read_page", "purchase"]) == RiskLevel.critical

    def test_empty_list_returns_low(self, clf):
        assert clf.classify_many([]) == RiskLevel.low

    def test_all_low(self, clf):
        assert clf.classify_many(["read_page", "scroll"]) == RiskLevel.low


class TestModuleLevelFunctions:
    def test_classify_module_level(self):
        assert classify("delete") == RiskLevel.critical

    def test_classify_many_module_level(self):
        assert classify_many(["read_page", "email_send"]) == RiskLevel.high
