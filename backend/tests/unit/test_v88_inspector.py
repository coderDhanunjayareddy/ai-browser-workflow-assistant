"""V8.8 Execution Authorization Framework — Unit tests: inspector.py (18 tests)."""
import time
import uuid
import pytest
from app.authorization import inspector as insp
from app.authorization import registry as reg
from app.authorization import analytics as anal
from app.authorization import timeline as tl
from app.authorization.models import AuthorizationStatus, make_authorization
from app.governance.models import make_contract


def _auth(mission_id="m-insp", authorized=True):
    return make_authorization(
        contract_id          = str(uuid.uuid4()),
        authorized           = authorized,
        authorization_reason = "ok" if authorized else "denied",
        risk_level           = "HIGH",
        expires_at           = time.time() + 3600,
        mission_id           = mission_id,
    )


@pytest.fixture(autouse=True)
def clean():
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()
    yield
    reg._reset_for_testing()
    anal._reset_for_testing()
    tl._reset_for_testing()


class TestInspectorStructure:

    def test_returns_dict(self):
        assert isinstance(insp.inspect("m-insp"), dict)

    def test_has_mission_id(self):
        r = insp.inspect("m-insp")
        assert r["mission_id"] == "m-insp"

    def test_has_total_authorizations(self):
        assert "total_authorizations" in insp.inspect("m-insp")

    def test_has_active_count(self):
        assert "active_count" in insp.inspect("m-insp")

    def test_has_denied_count(self):
        assert "denied_count" in insp.inspect("m-insp")

    def test_has_expired_count(self):
        assert "expired_count" in insp.inspect("m-insp")

    def test_has_revoked_count(self):
        assert "revoked_count" in insp.inspect("m-insp")

    def test_has_consumed_count(self):
        assert "consumed_count" in insp.inspect("m-insp")

    def test_has_executable_count(self):
        assert "executable_count" in insp.inspect("m-insp")

    def test_has_analytics(self):
        assert "analytics" in insp.inspect("m-insp")

    def test_has_registry_stats(self):
        assert "registry_stats" in insp.inspect("m-insp")

    def test_has_latency_ms(self):
        assert "latency_ms" in insp.inspect("m-insp")

    def test_has_risk_breakdown(self):
        assert "risk_breakdown" in insp.inspect("m-insp")


class TestInspectorCounts:

    def test_empty_mission(self):
        r = insp.inspect("m-empty")
        assert r["total_authorizations"] == 0
        assert r["active_count"] == 0

    def test_one_active(self):
        reg.add(_auth(mission_id="m-one", authorized=True))
        r = insp.inspect("m-one")
        assert r["total_authorizations"] == 1
        assert r["active_count"] == 1
        assert r["executable_count"] == 1

    def test_one_denied(self):
        reg.add(_auth(mission_id="m-denied", authorized=False))
        r = insp.inspect("m-denied")
        assert r["denied_count"] == 1
        assert r["active_count"] == 0

    def test_revoked_not_executable(self):
        a = _auth(mission_id="m-rev-insp")
        reg.add(a)
        reg.revoke(a.authorization_id)
        r = insp.inspect("m-rev-insp")
        assert r["revoked_count"] == 1
        assert r["executable_count"] == 0

    def test_latency_non_negative(self):
        r = insp.inspect("m-lat")
        assert r["latency_ms"] >= 0
