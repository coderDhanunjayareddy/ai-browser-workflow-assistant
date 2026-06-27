"""V8.8 Execution Authorization Framework — Unit tests: models.py (26 tests)."""
import time
import pytest
from app.authorization.models import (
    ExecutionAuthorization, AuthorizationStatus, ExecutionReadinessReport,
    make_authorization, EVALUATOR_VERSION, TRUST_SCORE_THRESHOLD,
)


def _make(authorized=True, ttl=3600.0, mission_id="m-m", contract_id=None) -> ExecutionAuthorization:
    import uuid
    return make_authorization(
        contract_id          = contract_id or str(uuid.uuid4()),
        authorized           = authorized,
        authorization_reason = "ok" if authorized else "denied",
        risk_level           = "HIGH",
        expires_at           = time.time() + ttl,
        mission_id           = mission_id,
        task_id              = "t-m",
    )


class TestAuthorizationStatusEnum:
    def test_active_value(self):   assert AuthorizationStatus.active.value   == "ACTIVE"
    def test_denied_value(self):   assert AuthorizationStatus.denied.value   == "DENIED"
    def test_expired_value(self):  assert AuthorizationStatus.expired.value  == "EXPIRED"
    def test_revoked_value(self):  assert AuthorizationStatus.revoked.value  == "REVOKED"
    def test_consumed_value(self): assert AuthorizationStatus.consumed.value == "CONSUMED"
    def test_from_string(self):    assert AuthorizationStatus("ACTIVE") == AuthorizationStatus.active


class TestExecutionAuthorizationFields:

    def test_has_authorization_id(self):
        a = _make()
        assert isinstance(a.authorization_id, str) and len(a.authorization_id) == 36

    def test_contract_id_stored(self):
        a = _make(contract_id="ctr-1")
        assert a.contract_id == "ctr-1"

    def test_authorized_true(self):
        assert _make(authorized=True).authorized is True

    def test_authorized_false(self):
        assert _make(authorized=False).authorized is False

    def test_default_status_active_when_authorized(self):
        assert _make(authorized=True).status == AuthorizationStatus.active

    def test_default_status_denied_when_not_authorized(self):
        assert _make(authorized=False).status == AuthorizationStatus.denied

    def test_evaluator_version(self):
        assert _make().evaluator_version == EVALUATOR_VERSION

    def test_risk_level_stored(self):
        assert _make().risk_level == "HIGH"

    def test_mission_id_stored(self):
        assert _make(mission_id="m-test").mission_id == "m-test"

    def test_expires_at_in_future(self):
        assert _make(ttl=3600.0).expires_at > time.time()

    def test_evaluated_at_recent(self):
        a = _make()
        assert abs(a.evaluated_at - time.time()) < 2.0

    def test_unique_ids(self):
        a, b = _make(), _make()
        assert a.authorization_id != b.authorization_id


class TestExecutionAuthorizationProperties:

    def test_is_active_true(self):
        assert _make(authorized=True).is_active is True

    def test_is_active_false_when_denied(self):
        a = _make(authorized=False)
        assert a.is_active is False

    def test_is_executable_true(self):
        a = _make(authorized=True, ttl=3600.0)
        assert a.is_executable is True

    def test_is_executable_false_when_not_authorized(self):
        a = _make(authorized=False)
        assert a.is_executable is False

    def test_is_executable_false_when_revoked(self):
        a = _make(authorized=True)
        a.status = AuthorizationStatus.revoked
        assert a.is_executable is False

    def test_is_expired_now_false_for_future(self):
        assert _make(ttl=3600.0).is_expired_now is False

    def test_is_expired_now_true_when_past(self):
        a = _make(ttl=0.001)
        time.sleep(0.01)
        assert a.is_expired_now is True


class TestExecutionAuthorizationToDict:

    def test_to_dict_keys(self):
        d = _make().to_dict()
        for key in ["authorization_id", "contract_id", "authorized", "status",
                    "authorization_reason", "risk_level", "expires_at", "is_executable"]:
            assert key in d

    def test_status_serialized_string(self):
        d = _make(authorized=True).to_dict()
        assert d["status"] == "ACTIVE"

    def test_denied_status_string(self):
        d = _make(authorized=False).to_dict()
        assert d["status"] == "DENIED"


class TestExecutionReadinessReport:

    def test_to_dict_keys(self):
        r = ExecutionReadinessReport(
            mission_id="m-r", mission_ready=True, contracts_ready=1,
            approvals_ready=1, trust_ready=True, blockers=[], readiness_score=1.0,
            evaluated_at=time.time(),
        )
        d = r.to_dict()
        for key in ["mission_id", "mission_ready", "contracts_ready", "approvals_ready",
                    "trust_ready", "blockers", "readiness_score", "evaluated_at"]:
            assert key in d

    def test_score_range(self):
        r = ExecutionReadinessReport(
            mission_id="m-r", mission_ready=False, contracts_ready=0,
            approvals_ready=0, trust_ready=False, blockers=["x"], readiness_score=0.0,
            evaluated_at=time.time(),
        )
        assert 0.0 <= r.readiness_score <= 1.0


class TestConstants:
    def test_evaluator_version(self):       assert isinstance(EVALUATOR_VERSION, str)
    def test_trust_score_threshold(self):   assert 0.0 < TRUST_SCORE_THRESHOLD < 1.0
