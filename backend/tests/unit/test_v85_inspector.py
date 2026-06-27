"""V8.5 Governance Layer — Unit tests: inspector.py (18 tests)."""
import time
import pytest
from app.governance import inspector as insp
from app.governance import registry as reg
from app.governance import analytics as anal
from app.governance import timeline as tl
from app.governance.models import make_contract, ContractStatus


def _make(mission_id="m-insp", approved=True) -> object:
    return make_contract(
        approval_id = "appr-insp-1",
        approved    = approved,
        approved_by = "tester",
        approved_at = time.time(),
        source_type = "TRUST_ENGINE",
        source_id   = "src-insp",
        risk_level  = "HIGH",
        mission_id  = mission_id,
        ttl_seconds = 3600.0,
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
        result = insp.inspect("m-insp")
        assert isinstance(result, dict)

    def test_has_mission_id(self):
        result = insp.inspect("m-insp")
        assert result["mission_id"] == "m-insp"

    def test_has_total_contracts(self):
        result = insp.inspect("m-insp")
        assert "total_contracts" in result

    def test_has_active_count(self):
        result = insp.inspect("m-insp")
        assert "active_count" in result

    def test_has_expired_count(self):
        result = insp.inspect("m-insp")
        assert "expired_count" in result

    def test_has_revoked_count(self):
        result = insp.inspect("m-insp")
        assert "revoked_count" in result

    def test_has_consumed_count(self):
        result = insp.inspect("m-insp")
        assert "consumed_count" in result

    def test_has_execution_eligible(self):
        result = insp.inspect("m-insp")
        assert "execution_eligible" in result

    def test_has_active_contracts_list(self):
        result = insp.inspect("m-insp")
        assert "active_contracts" in result

    def test_has_source_breakdown(self):
        result = insp.inspect("m-insp")
        assert "source_breakdown" in result

    def test_has_analytics(self):
        result = insp.inspect("m-insp")
        assert "analytics" in result

    def test_has_registry_stats(self):
        result = insp.inspect("m-insp")
        assert "registry_stats" in result

    def test_has_latency_ms(self):
        result = insp.inspect("m-insp")
        assert "latency_ms" in result


class TestInspectorCounts:

    def test_empty_mission_zero_contracts(self):
        result = insp.inspect("m-empty")
        assert result["total_contracts"] == 0
        assert result["active_count"] == 0

    def test_with_one_active(self):
        c = _make(mission_id="m-one")
        reg.add(c)
        result = insp.inspect("m-one")
        assert result["total_contracts"] == 1
        assert result["active_count"] == 1
        assert result["execution_eligible"] == 1

    def test_with_revoked_not_eligible(self):
        c = _make(mission_id="m-rev")
        reg.add(c)
        reg.revoke(c.contract_id)
        result = insp.inspect("m-rev")
        assert result["revoked_count"] == 1
        assert result["execution_eligible"] == 0

    def test_latency_ms_is_non_negative(self):
        result = insp.inspect("m-latency")
        assert result["latency_ms"] >= 0

    def test_source_breakdown_populated(self):
        c = _make(mission_id="m-src")
        reg.add(c)
        result = insp.inspect("m-src")
        assert result["source_breakdown"].get("TRUST_ENGINE", 0) >= 1
