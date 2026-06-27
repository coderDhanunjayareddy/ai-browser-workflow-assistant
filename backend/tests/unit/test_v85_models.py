"""V8.5 Governance Layer — Unit tests: models.py (22 tests)."""
import time
import pytest
from app.governance.models import (
    GovernanceContract, ContractStatus, EligibilityResult,
    ExecutionAuthorization, make_contract,
    CONTRACT_TTL_SECONDS, CONTRACT_VERSION,
)


def _make(approved=True, ttl=3600.0, **kw) -> GovernanceContract:
    return make_contract(
        approval_id = "appr-model-1",
        approved    = approved,
        approved_by = "tester",
        approved_at = time.time(),
        source_type = "TRUST_ENGINE",
        source_id   = "src-1",
        risk_level  = "HIGH",
        mission_id  = "m-test",
        ttl_seconds = ttl,
        **kw,
    )


class TestGovernanceContractFields:

    def test_has_contract_id(self):
        c = _make()
        assert isinstance(c.contract_id, str) and len(c.contract_id) > 8

    def test_approved_true(self):
        c = _make(approved=True)
        assert c.approved is True

    def test_approved_false(self):
        c = _make(approved=False)
        assert c.approved is False

    def test_default_status_active(self):
        c = _make()
        assert c.status == ContractStatus.active

    def test_source_type_stored(self):
        c = _make()
        assert c.source_type == "TRUST_ENGINE"

    def test_risk_level_stored(self):
        c = _make()
        assert c.risk_level == "HIGH"

    def test_mission_id_stored(self):
        c = _make()
        assert c.mission_id == "m-test"

    def test_contract_version(self):
        c = _make()
        assert c.contract_version == CONTRACT_VERSION

    def test_execution_allowed_when_approved(self):
        c = _make(approved=True)
        assert c.execution_allowed is True

    def test_execution_allowed_false_when_not_approved(self):
        c = _make(approved=False)
        assert c.execution_allowed is False

    def test_expires_at_in_future(self):
        c = _make(ttl=3600.0)
        assert c.expires_at > time.time()

    def test_expires_at_uses_ttl(self):
        c = _make(ttl=100.0)
        assert abs((c.expires_at - c.created_at) - 100.0) < 1.0


class TestGovernanceContractProperties:

    def test_is_active(self):
        c = _make()
        assert c.is_active is True

    def test_is_eligible_active_approved(self):
        c = _make(approved=True)
        assert c.is_eligible is True

    def test_is_eligible_false_when_not_approved(self):
        c = _make(approved=False)
        assert c.is_eligible is False

    def test_is_eligible_false_when_revoked(self):
        c = _make()
        c.status = ContractStatus.revoked
        assert c.is_eligible is False

    def test_is_eligible_false_when_expired(self):
        c = _make()
        c.status = ContractStatus.expired
        assert c.is_eligible is False

    def test_is_expired_now_false_for_future_ttl(self):
        c = _make(ttl=3600.0)
        assert c.is_expired_now is False


class TestGovernanceContractToDict:

    def test_to_dict_keys(self):
        d = _make().to_dict()
        for key in ["contract_id", "approval_id", "approved", "status",
                    "execution_allowed", "risk_level", "source_type"]:
            assert key in d

    def test_status_serialized_as_string(self):
        d = _make().to_dict()
        assert d["status"] == "ACTIVE"


class TestMakeContract:

    def test_unique_ids(self):
        a = _make()
        b = _make()
        assert a.contract_id != b.contract_id


class TestEligibilityResult:

    def test_to_authorization(self):
        er = EligibilityResult(
            eligible=True, contract_id="cid-1", reason="ok",
            checked_at=time.time(), conditions={}
        )
        auth = er.to_authorization()
        assert isinstance(auth, ExecutionAuthorization)
        assert auth.authorized is True

    def test_to_dict_has_eligible(self):
        er = EligibilityResult(
            eligible=False, contract_id="cid-2", reason="denied",
            checked_at=time.time(), conditions={}
        )
        d = er.to_dict()
        assert d["eligible"] is False


class TestExecutionAuthorization:

    def test_to_dict(self):
        auth = ExecutionAuthorization(
            contract_id="cid-3", authorized=True, reason="ok"
        )
        d = auth.to_dict()
        assert d["authorized"] is True
        assert d["contract_id"] == "cid-3"
