"""V8.5 Governance Layer — Unit tests: registry.py (28 tests)."""
import time
import pytest
from app.governance import registry as reg
from app.governance.models import ContractStatus, make_contract


def _make(mission_id="m-reg", ttl=3600.0, approved=True, approval_id=None) -> object:
    import uuid
    return make_contract(
        approval_id = approval_id or str(uuid.uuid4()),
        approved    = approved,
        approved_by = "tester",
        approved_at = time.time(),
        source_type = "TRUST_ENGINE",
        source_id   = "src-reg",
        risk_level  = "HIGH",
        mission_id  = mission_id,
        ttl_seconds = ttl,
    )


@pytest.fixture(autouse=True)
def clean():
    reg._reset_for_testing()
    yield
    reg._reset_for_testing()


class TestRegistryAdd:

    def test_add_increases_count(self):
        c = _make()
        reg.add(c)
        assert reg.count() == 1

    def test_add_two(self):
        reg.add(_make())
        reg.add(_make())
        assert reg.count() == 2

    def test_add_then_get(self):
        c = _make()
        reg.add(c)
        found = reg.get(c.contract_id)
        assert found is not None
        assert found.contract_id == c.contract_id


class TestRegistryGet:

    def test_get_missing_returns_none(self):
        assert reg.get("nonexistent-id") is None

    def test_get_for_approval(self):
        c = _make(approval_id="appr-lookup-1")
        reg.add(c)
        found = reg.get_for_approval("appr-lookup-1")
        assert found is not None

    def test_get_for_approval_missing(self):
        assert reg.get_for_approval("missing-appr") is None


class TestRegistryRevoke:

    def test_revoke_active(self):
        c = _make()
        reg.add(c)
        ok = reg.revoke(c.contract_id, reason="test")
        assert ok is True
        found = reg.get(c.contract_id)
        assert found.status == ContractStatus.revoked
        assert found.revoked_reason == "test"

    def test_revoke_already_revoked(self):
        c = _make()
        reg.add(c)
        reg.revoke(c.contract_id)
        ok2 = reg.revoke(c.contract_id)
        assert ok2 is False

    def test_revoke_missing(self):
        assert reg.revoke("no-such-id") is False


class TestRegistryExpire:

    def test_expire_active(self):
        c = _make()
        reg.add(c)
        ok = reg.expire(c.contract_id)
        assert ok is True
        found = reg.get(c.contract_id)
        assert found.status == ContractStatus.expired

    def test_expire_already_expired(self):
        c = _make()
        reg.add(c)
        reg.expire(c.contract_id)
        assert reg.expire(c.contract_id) is False


class TestRegistryConsume:

    def test_consume_active(self):
        c = _make()
        reg.add(c)
        ok = reg.consume(c.contract_id)
        assert ok is True
        found = reg.get(c.contract_id)
        assert found.status == ContractStatus.consumed
        assert found.consumed_at is not None

    def test_consume_already_consumed(self):
        c = _make()
        reg.add(c)
        reg.consume(c.contract_id)
        assert reg.consume(c.contract_id) is False


class TestRegistryListViews:

    def test_list_all(self):
        reg.add(_make())
        reg.add(_make())
        assert len(reg.list_all()) == 2

    def test_list_active(self):
        c1 = _make()
        c2 = _make()
        reg.add(c1)
        reg.add(c2)
        reg.revoke(c1.contract_id)
        active = reg.list_active()
        assert len(active) == 1
        assert active[0].contract_id == c2.contract_id

    def test_list_for_mission(self):
        reg.add(_make(mission_id="m-A"))
        reg.add(_make(mission_id="m-A"))
        reg.add(_make(mission_id="m-B"))
        assert len(reg.list_for_mission("m-A")) == 2
        assert len(reg.list_for_mission("m-B")) == 1

    def test_list_limit_respected(self):
        for _ in range(5):
            reg.add(_make())
        assert len(reg.list_all(limit=2)) == 2


class TestRegistrySummary:

    def test_summary_for_mission(self):
        c = _make(mission_id="m-sum")
        reg.add(c)
        s = reg.summary_for_mission("m-sum")
        assert s["total"] == 1
        assert s["active_contracts"] == 1
        assert s["execution_eligible"] == 1

    def test_summary_empty_mission(self):
        s = reg.summary_for_mission("no-such-mission")
        assert s["total"] == 0


class TestRegistryStats:

    def test_stats_fields(self):
        s = reg.stats()
        for k in ["cached_items", "total_added", "total_evicted", "active_count"]:
            assert k in s

    def test_stats_after_add(self):
        reg.add(_make())
        s = reg.stats()
        assert s["total_added"] == 1
