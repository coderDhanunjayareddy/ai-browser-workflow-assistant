"""V8.5 Governance Layer — Unit tests: eligibility.py (18 tests)."""
import time
import pytest
from app.governance import eligibility as elig
from app.governance.models import ContractStatus, make_contract


def _make(approved=True, ttl=3600.0) -> object:
    return make_contract(
        approval_id = "appr-elig-1",
        approved    = approved,
        approved_by = "tester",
        approved_at = time.time(),
        source_type = "TRUST_ENGINE",
        source_id   = "src-e",
        risk_level  = "HIGH",
        ttl_seconds = ttl,
    )


class TestEligibilityEngineCheck:

    def test_active_approved_is_eligible(self):
        c = _make(approved=True)
        r = elig.check(c)
        assert r.eligible is True

    def test_not_approved_not_eligible(self):
        c = _make(approved=False)
        r = elig.check(c)
        assert r.eligible is False

    def test_revoked_not_eligible(self):
        c = _make()
        c.status = ContractStatus.revoked
        r = elig.check(c)
        assert r.eligible is False

    def test_consumed_not_eligible(self):
        c = _make()
        c.status = ContractStatus.consumed
        r = elig.check(c)
        assert r.eligible is False

    def test_expired_not_eligible(self):
        c = _make()
        c.status = ContractStatus.expired
        r = elig.check(c)
        assert r.eligible is False

    def test_expired_by_wall_clock(self):
        c = _make(ttl=0.001)
        time.sleep(0.01)
        r = elig.check(c)
        assert r.eligible is False

    def test_conditions_all_true_when_eligible(self):
        c = _make()
        r = elig.check(c)
        assert all(r.conditions.values())

    def test_conditions_has_five_keys(self):
        c = _make()
        r = elig.check(c)
        assert len(r.conditions) == 5

    def test_reason_contains_denied_when_not_eligible(self):
        c = _make(approved=False)
        r = elig.check(c)
        assert "denied" in r.reason.lower()

    def test_reason_satisfied_when_eligible(self):
        c = _make()
        r = elig.check(c)
        assert "satisfied" in r.reason.lower()

    def test_checked_at_is_recent(self):
        c = _make()
        r = elig.check(c)
        assert abs(r.checked_at - time.time()) < 2.0


class TestEligibilityConditionNames:

    def test_has_is_active_condition(self):
        c = _make()
        r = elig.check(c)
        assert "is_active" in r.conditions

    def test_has_approved_condition(self):
        c = _make()
        r = elig.check(c)
        assert "approved" in r.conditions

    def test_has_not_expired_condition(self):
        c = _make()
        r = elig.check(c)
        assert "not_expired" in r.conditions

    def test_has_not_revoked_condition(self):
        c = _make()
        r = elig.check(c)
        assert "not_revoked" in r.conditions

    def test_has_not_consumed_condition(self):
        c = _make()
        r = elig.check(c)
        assert "not_consumed" in r.conditions


class TestEligibilityAuthorize:

    def test_authorize_eligible(self):
        c = _make()
        auth = elig.authorize(c)
        assert auth.authorized is True

    def test_authorize_not_eligible(self):
        c = _make(approved=False)
        auth = elig.authorize(c)
        assert auth.authorized is False

    def test_authorize_has_contract_id(self):
        c = _make()
        auth = elig.authorize(c)
        assert auth.contract_id == c.contract_id
