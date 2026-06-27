"""V8.8 Execution Authorization Framework — Unit tests: engine.py (24 tests)."""
import time
import pytest
from app.authorization import engine as eng
from app.authorization.models import AuthorizationStatus
from app.governance.models import make_contract, ContractStatus


def _contract(approved=True, ttl=3600.0, execution_allowed=True, mission_id="m-eng"):
    c = make_contract(
        approval_id = "appr-eng",
        approved    = approved,
        approved_by = "tester",
        approved_at = time.time(),
        source_type = "TRUST_ENGINE",
        source_id   = "src-e",
        risk_level  = "HIGH",
        mission_id  = mission_id,
        ttl_seconds = ttl,
    )
    c.execution_allowed = execution_allowed
    return c


class TestEngineAuthorized:

    def test_all_conditions_pass(self):
        c = _contract()
        r = eng.evaluate(c)
        assert r.authorized is True

    def test_status_active_when_authorized(self):
        c = _contract()
        r = eng.evaluate(c)
        assert r.status == AuthorizationStatus.active

    def test_conditions_6_keys(self):
        c = _contract()
        r = eng.evaluate(c)
        assert len(r.conditions) == 6

    def test_all_conditions_true(self):
        c = _contract()
        r = eng.evaluate(c)
        assert all(r.conditions.values())

    def test_reason_contains_satisfied(self):
        r = eng.evaluate(_contract())
        assert "satisfied" in r.authorization_reason.lower() or "conditions" in r.authorization_reason.lower()

    def test_contract_id_propagated(self):
        c = _contract()
        r = eng.evaluate(c)
        assert r.contract_id == c.contract_id

    def test_mission_id_propagated(self):
        c = _contract(mission_id="m-prop")
        r = eng.evaluate(c)
        assert r.mission_id == "m-prop"

    def test_risk_level_propagated(self):
        c = _contract()
        r = eng.evaluate(c)
        assert r.risk_level == "HIGH"

    def test_expires_at_matches_contract(self):
        c = _contract()
        r = eng.evaluate(c)
        assert r.expires_at == c.expires_at


class TestEngineDenied:

    def test_not_approved(self):
        c = _contract(approved=False)
        r = eng.evaluate(c)
        assert r.authorized is False

    def test_not_approved_status_denied(self):
        c = _contract(approved=False)
        r = eng.evaluate(c)
        assert r.status == AuthorizationStatus.denied

    def test_execution_not_allowed(self):
        c = _contract(execution_allowed=False)
        r = eng.evaluate(c)
        assert r.authorized is False

    def test_revoked_contract(self):
        c = _contract()
        c.status = ContractStatus.revoked
        r = eng.evaluate(c)
        assert r.authorized is False

    def test_consumed_contract(self):
        c = _contract()
        c.status = ContractStatus.consumed
        r = eng.evaluate(c)
        assert r.authorized is False

    def test_expired_by_wall_clock(self):
        c = _contract(ttl=0.001)
        time.sleep(0.01)
        r = eng.evaluate(c)
        assert r.authorized is False

    def test_reason_contains_denied(self):
        c = _contract(approved=False)
        r = eng.evaluate(c)
        assert "denied" in r.authorization_reason.lower()

    def test_reason_mentions_failed_condition(self):
        c = _contract(approved=False)
        r = eng.evaluate(c)
        assert "contract_approved" in r.authorization_reason or "approved" in r.authorization_reason.lower()


class TestEngineConditions:

    def test_contract_active_condition(self):
        c = _contract()
        r = eng.evaluate(c)
        assert "contract_active" in r.conditions

    def test_contract_approved_condition(self):
        c = _contract()
        r = eng.evaluate(c)
        assert "contract_approved" in r.conditions

    def test_execution_allowed_condition(self):
        c = _contract()
        r = eng.evaluate(c)
        assert "execution_allowed" in r.conditions

    def test_not_revoked_condition(self):
        c = _contract()
        r = eng.evaluate(c)
        assert "not_revoked" in r.conditions

    def test_not_consumed_condition(self):
        c = _contract()
        r = eng.evaluate(c)
        assert "not_consumed" in r.conditions

    def test_not_expired_condition(self):
        c = _contract()
        r = eng.evaluate(c)
        assert "not_expired" in r.conditions


class TestEngineTrustAndMission:

    def test_low_trust_still_authorized(self):
        c = _contract()
        r = eng.evaluate(c, trust_score=0.1)
        assert r.authorized is True    # trust does NOT affect outcome

    def test_low_trust_in_reason(self):
        c = _contract()
        r = eng.evaluate(c, trust_score=0.1)
        assert "trust" in r.authorization_reason.lower()

    def test_high_trust_no_note(self):
        c = _contract()
        r = eng.evaluate(c, trust_score=0.9)
        assert "trust" not in r.authorization_reason.lower()

    def test_inactive_mission_state_still_authorized(self):
        c = _contract()
        r = eng.evaluate(c, mission_state="PAUSED")
        assert r.authorized is True    # mission state does NOT affect outcome

    def test_inactive_mission_state_in_reason(self):
        c = _contract()
        r = eng.evaluate(c, mission_state="PAUSED")
        assert "PAUSED" in r.authorization_reason

    def test_trust_score_stored(self):
        c = _contract()
        r = eng.evaluate(c, trust_score=0.7)
        assert r.trust_score == 0.7
