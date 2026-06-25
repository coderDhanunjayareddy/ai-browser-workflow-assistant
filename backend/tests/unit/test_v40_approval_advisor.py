"""
V4.0 Unit Tests — ApprovalPolicyAdvisor.

Tests cover:
  - SAFE for search, navigate, no-opportunity
  - REQUIRES_APPROVAL for book, register, schedule, download, rent, apply
  - HIGH_RISK for purchase, communicate, and phrase-level overrides
  - Phrase overrides trump action_type defaults
"""
import pytest
from app.intelligence.models import ActionType, ApprovalLevel, ExecutionOpportunity
from app.intelligence.approval_advisor import ApprovalPolicyAdvisor


def _make_opp(action_type: ActionType, detected: bool = True) -> ExecutionOpportunity:
    return ExecutionOpportunity(
        detected=detected,
        confidence=0.9 if detected else 0.0,
        action_type=action_type,
        required_entities=[],
        missing_information=[],
        workflow_candidate=True,
        raw_action_keywords=[],
    )


@pytest.fixture
def adv():
    return ApprovalPolicyAdvisor()


class TestSafeLevel:
    def test_not_detected_is_safe(self, adv):
        opp = _make_opp(ActionType.unknown, detected=False)
        assert adv.classify(opp, "research flights") == ApprovalLevel.safe

    def test_navigate_is_safe(self, adv):
        opp = _make_opp(ActionType.navigate)
        assert adv.classify(opp, "open amazon") == ApprovalLevel.safe

    def test_search_is_safe(self, adv):
        opp = _make_opp(ActionType.search)
        assert adv.classify(opp, "search for flights") == ApprovalLevel.safe

    def test_unknown_detected_false_is_safe(self, adv):
        opp = _make_opp(ActionType.unknown, detected=False)
        assert adv.classify(opp, "") == ApprovalLevel.safe


class TestRequiresApprovalLevel:
    def test_book_requires_approval(self, adv):
        opp = _make_opp(ActionType.book)
        assert adv.classify(opp, "book a flight") == ApprovalLevel.requires_approval

    def test_register_requires_approval(self, adv):
        opp = _make_opp(ActionType.register)
        assert adv.classify(opp, "sign up") == ApprovalLevel.requires_approval

    def test_schedule_requires_approval(self, adv):
        opp = _make_opp(ActionType.schedule)
        assert adv.classify(opp, "schedule appointment") == ApprovalLevel.requires_approval

    def test_download_requires_approval(self, adv):
        opp = _make_opp(ActionType.download)
        assert adv.classify(opp, "download the app") == ApprovalLevel.requires_approval

    def test_rent_requires_approval(self, adv):
        opp = _make_opp(ActionType.rent)
        assert adv.classify(opp, "rent a car") == ApprovalLevel.requires_approval

    def test_apply_requires_approval(self, adv):
        opp = _make_opp(ActionType.apply)
        assert adv.classify(opp, "apply for the job") == ApprovalLevel.requires_approval


class TestHighRiskLevel:
    def test_purchase_is_high_risk(self, adv):
        opp = _make_opp(ActionType.purchase)
        assert adv.classify(opp, "buy the laptop") == ApprovalLevel.high_risk

    def test_communicate_is_high_risk(self, adv):
        opp = _make_opp(ActionType.communicate)
        assert adv.classify(opp, "send email") == ApprovalLevel.high_risk

    def test_pay_phrase_overrides_to_high_risk(self, adv):
        opp = _make_opp(ActionType.book)  # normally REQUIRES_APPROVAL
        assert adv.classify(opp, "book and pay now") == ApprovalLevel.high_risk

    def test_delete_phrase_overrides_to_high_risk(self, adv):
        opp = _make_opp(ActionType.navigate)  # normally SAFE
        assert adv.classify(opp, "delete my account") == ApprovalLevel.high_risk

    def test_place_order_phrase_overrides(self, adv):
        opp = _make_opp(ActionType.book)
        assert adv.classify(opp, "place order for ticket") == ApprovalLevel.high_risk

    def test_send_message_phrase_overrides(self, adv):
        opp = _make_opp(ActionType.navigate)
        assert adv.classify(opp, "send message to friend") == ApprovalLevel.high_risk
