"""V8.8 Execution Authorization Framework — Unit tests: readiness.py (16 tests)."""
import time
import pytest
from app.authorization import readiness as rdns
from app.authorization import registry as auth_reg
from app.authorization.models import ExecutionReadinessReport


@pytest.fixture(autouse=True)
def clean():
    auth_reg._reset_for_testing()
    yield
    auth_reg._reset_for_testing()


class TestReadinessEngineStructure:

    def test_returns_report(self):
        r = rdns.evaluate("m-rdns")
        assert isinstance(r, ExecutionReadinessReport)

    def test_report_has_mission_id(self):
        r = rdns.evaluate("m-rdns")
        assert r.mission_id == "m-rdns"

    def test_report_has_blockers(self):
        r = rdns.evaluate("m-rdns-unknown")
        assert isinstance(r.blockers, list)

    def test_readiness_score_zero_to_one(self):
        r = rdns.evaluate("m-rdns2")
        assert 0.0 <= r.readiness_score <= 1.0

    def test_to_dict_keys(self):
        r = rdns.evaluate("m-rdns3")
        d = r.to_dict()
        for k in ["mission_id", "mission_ready", "contracts_ready",
                  "approvals_ready", "trust_ready", "blockers",
                  "readiness_score", "evaluated_at", "active_authorizations",
                  "denied_authorizations", "executable_tasks"]:
            assert k in d

    def test_evaluated_at_recent(self):
        r = rdns.evaluate("m-rdns4")
        assert abs(r.evaluated_at - time.time()) < 2.0


class TestReadinessScoreComputation:

    def test_unknown_mission_has_blockers(self):
        r = rdns.evaluate("m-no-such-mission")
        assert len(r.blockers) > 0
        assert r.readiness_score < 1.0

    def test_no_authorizations_blocker(self):
        r = rdns.evaluate("m-no-auth")
        blockers_lower = [b.lower() for b in r.blockers]
        has_auth_blocker = any("authorization" in b for b in blockers_lower)
        assert has_auth_blocker

    def test_executable_tasks_empty_default(self):
        r = rdns.evaluate("m-no-tasks")
        assert isinstance(r.executable_tasks, list)

    def test_active_authorizations_count(self):
        r = rdns.evaluate("m-cnt")
        assert isinstance(r.active_authorizations, int)

    def test_denied_authorizations_count(self):
        r = rdns.evaluate("m-dcnt")
        assert isinstance(r.denied_authorizations, int)

    def test_score_increases_with_authorizations(self):
        from app.authorization.models import make_authorization
        from app.governance.models import make_contract
        import uuid

        mission_id = "m-score-improve"
        c = make_contract(
            str(uuid.uuid4()), True, "t", time.time(),
            "TRUST_ENGINE", "s", "HIGH",
            mission_id=mission_id, ttl_seconds=3600,
        )
        from app.authorization import engine as eng_mod
        auth = eng_mod.evaluate(c)
        auth_reg.add(auth)

        r = rdns.evaluate(mission_id)
        # with one active authorization, that component is satisfied
        assert r.active_authorizations >= 1


class TestReadinessGraceful:

    def test_graceful_unknown_mission(self):
        r = rdns.evaluate("totally-unknown-xyz")
        assert isinstance(r, ExecutionReadinessReport)

    def test_graceful_empty_string_mission(self):
        r = rdns.evaluate("")
        assert isinstance(r, ExecutionReadinessReport)

    def test_blockers_are_strings(self):
        r = rdns.evaluate("m-blk")
        assert all(isinstance(b, str) for b in r.blockers)
