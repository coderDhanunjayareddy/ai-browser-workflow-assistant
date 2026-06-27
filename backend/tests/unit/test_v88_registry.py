"""V8.8 Execution Authorization Framework — Unit tests: registry.py (30 tests)."""
import time
import uuid
import pytest
from app.authorization import registry as reg
from app.authorization import engine as eng
from app.authorization.models import AuthorizationStatus, make_authorization
from app.governance.models import make_contract


def _contract(mission_id="m-reg", ttl=3600.0):
    return make_contract(
        approval_id = str(uuid.uuid4()),
        approved    = True,
        approved_by = "tester",
        approved_at = time.time(),
        source_type = "TRUST_ENGINE",
        source_id   = "src-r",
        risk_level  = "HIGH",
        mission_id  = mission_id,
        ttl_seconds = ttl,
    )


def _auth(mission_id="m-reg", contract_id=None, authorized=True, task_id=None):
    return make_authorization(
        contract_id          = contract_id or str(uuid.uuid4()),
        authorized           = authorized,
        authorization_reason = "ok" if authorized else "denied",
        risk_level           = "HIGH",
        expires_at           = time.time() + 3600,
        mission_id           = mission_id,
        task_id              = task_id,
    )


@pytest.fixture(autouse=True)
def clean():
    reg._reset_for_testing()
    yield
    reg._reset_for_testing()


class TestRegistryAddGet:

    def test_add_increases_count(self):
        reg.add(_auth())
        assert reg.count() == 1

    def test_add_two(self):
        reg.add(_auth()); reg.add(_auth())
        assert reg.count() == 2

    def test_get_found(self):
        a = _auth()
        reg.add(a)
        found = reg.get(a.authorization_id)
        assert found is not None
        assert found.authorization_id == a.authorization_id

    def test_get_missing(self):
        assert reg.get("nonexistent") is None

    def test_get_for_contract(self):
        ctr_id = str(uuid.uuid4())
        a = _auth(contract_id=ctr_id)
        reg.add(a)
        found = reg.get_for_contract(ctr_id)
        assert found is not None
        assert found.contract_id == ctr_id

    def test_get_for_contract_missing(self):
        assert reg.get_for_contract("no-contract") is None

    def test_later_auth_overwrites_contract_index(self):
        ctr_id = str(uuid.uuid4())
        a1 = _auth(contract_id=ctr_id)
        a2 = _auth(contract_id=ctr_id)
        reg.add(a1)
        reg.add(a2)
        found = reg.get_for_contract(ctr_id)
        assert found.authorization_id == a2.authorization_id


class TestRegistryRevoke:

    def test_revoke_active(self):
        a = _auth(authorized=True)
        reg.add(a)
        ok = reg.revoke(a.authorization_id, reason="test")
        assert ok is True
        found = reg.get(a.authorization_id)
        assert found.status == AuthorizationStatus.revoked
        assert found.revoked_reason == "test"

    def test_revoke_twice_false(self):
        a = _auth()
        reg.add(a)
        reg.revoke(a.authorization_id)
        assert reg.revoke(a.authorization_id) is False

    def test_revoke_denied_false(self):
        a = _auth(authorized=False)
        reg.add(a)
        assert reg.revoke(a.authorization_id) is False

    def test_revoke_missing_false(self):
        assert reg.revoke("no-id") is False


class TestRegistryExpireConsume:

    def test_expire_active(self):
        a = _auth()
        reg.add(a)
        ok = reg.expire(a.authorization_id)
        assert ok is True
        assert reg.get(a.authorization_id).status == AuthorizationStatus.expired

    def test_expire_already_expired_false(self):
        a = _auth()
        reg.add(a)
        reg.expire(a.authorization_id)
        assert reg.expire(a.authorization_id) is False

    def test_consume_active(self):
        a = _auth()
        reg.add(a)
        ok = reg.consume(a.authorization_id)
        assert ok is True
        found = reg.get(a.authorization_id)
        assert found.status == AuthorizationStatus.consumed
        assert found.consumed_at is not None

    def test_consume_twice_false(self):
        a = _auth()
        reg.add(a)
        reg.consume(a.authorization_id)
        assert reg.consume(a.authorization_id) is False


class TestRegistryListViews:

    def test_list_all(self):
        reg.add(_auth()); reg.add(_auth())
        assert len(reg.list_all()) == 2

    def test_list_for_mission(self):
        reg.add(_auth(mission_id="m-A"))
        reg.add(_auth(mission_id="m-A"))
        reg.add(_auth(mission_id="m-B"))
        assert len(reg.list_for_mission("m-A")) == 2

    def test_list_for_task(self):
        reg.add(_auth(task_id="t-1"))
        reg.add(_auth(task_id="t-1"))
        reg.add(_auth(task_id="t-2"))
        assert len(reg.list_for_task("t-1")) == 2

    def test_list_executable(self):
        reg.add(_auth(authorized=True))
        reg.add(_auth(authorized=False))
        assert len(reg.list_executable()) == 1

    def test_list_limit(self):
        for _ in range(5): reg.add(_auth())
        assert len(reg.list_all(limit=2)) == 2

    def test_count_by_status(self):
        reg.add(_auth(authorized=True))
        reg.add(_auth(authorized=False))
        assert reg.count_by_status(AuthorizationStatus.active) == 1
        assert reg.count_by_status(AuthorizationStatus.denied) == 1

    def test_history_for_contract(self):
        ctr_id = str(uuid.uuid4())
        a1 = _auth(contract_id=ctr_id)
        a2 = _auth(contract_id=ctr_id)
        reg.add(a1)
        reg.add(a2)
        hist = reg.history_for_contract(ctr_id)
        assert len(hist) == 2


class TestRegistrySummary:

    def test_summary_for_mission(self):
        reg.add(_auth(mission_id="m-sum", authorized=True))
        reg.add(_auth(mission_id="m-sum", authorized=False))
        s = reg.summary_for_mission("m-sum")
        assert s["total"] == 2
        assert s["active_authorizations"] == 1
        assert s["denied_authorizations"] == 1

    def test_summary_empty_mission(self):
        s = reg.summary_for_mission("no-such")
        assert s["total"] == 0

    def test_stats_fields(self):
        s = reg.stats()
        for k in ["cached_items", "total_added", "total_evicted", "active_count"]:
            assert k in s

    def test_stats_after_add(self):
        reg.add(_auth())
        s = reg.stats()
        assert s["total_added"] == 1
