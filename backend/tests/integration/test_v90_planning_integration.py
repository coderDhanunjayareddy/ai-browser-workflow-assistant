"""
V9.0 Execution Planning Layer — Integration tests.

Exercises the /plans REST API plus cross-layer integration with the
V8.8 authorization layer, V5.0 mission inspector, and V8.9 runtime layer.
"""
import time
import uuid
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.execution_planning import registry as plan_reg
from app.execution_planning import analytics as plan_anal
from app.execution_planning import timeline as plan_tl
from app.authorization import registry as auth_reg
from app.authorization.models import make_authorization
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean():
    plan_reg._reset_for_testing()
    plan_anal._reset_for_testing()
    plan_tl._reset_for_testing()
    auth_reg._reset_for_testing()
    mission_store._reset_for_testing()
    yield
    plan_reg._reset_for_testing()
    plan_anal._reset_for_testing()
    plan_tl._reset_for_testing()
    auth_reg._reset_for_testing()
    mission_store._reset_for_testing()


def _setup_auth(mission="m-1", task="t-1", authorized=True, active=True, risk="HIGH"):
    auth = make_authorization("ctr-1", authorized, "ok", risk, time.time() + 3600,
                              mission_id=mission, task_id=task)
    auth_reg.add(auth)
    if mission:
        state = MissionState.active if active else MissionState.paused
        m = Mission(mission, "title", "objective", state, task_ids=[task] if task else [])
        mission_store.put(m)
    return auth


# ── POST /plans/create/{authorization_id} ─────────────────────────────────────

class TestCreateEndpoint:

    def test_create_200(self):
        a = _setup_auth()
        r = client.post(f"/plans/create/{a.authorization_id}")
        assert r.status_code == 200

    def test_create_returns_plan_id(self):
        a = _setup_auth()
        r = client.post(f"/plans/create/{a.authorization_id}")
        assert r.json()["plan_id"].startswith("plan-")

    def test_create_status_draft(self):
        a = _setup_auth()
        r = client.post(f"/plans/create/{a.authorization_id}")
        assert r.json()["status"] == "DRAFT"

    def test_create_has_steps(self):
        a = _setup_auth()
        r = client.post(f"/plans/create/{a.authorization_id}")
        assert len(r.json()["steps"]) == 3

    def test_create_authorization_id(self):
        a = _setup_auth()
        r = client.post(f"/plans/create/{a.authorization_id}")
        assert r.json()["authorization_id"] == a.authorization_id

    def test_create_missing_auth_404(self):
        r = client.post("/plans/create/no-such-auth")
        assert r.status_code == 404

    def test_create_denied_auth_409(self):
        a = _setup_auth(authorized=False)
        r = client.post(f"/plans/create/{a.authorization_id}")
        assert r.status_code == 409

    def test_create_stores_in_registry(self):
        a = _setup_auth()
        client.post(f"/plans/create/{a.authorization_id}")
        assert plan_reg.count() == 1

    def test_create_records_analytics(self):
        a = _setup_auth()
        client.post(f"/plans/create/{a.authorization_id}")
        assert client.get("/plans/analytics").json()["plans_created"] == 1


# ── POST /plans/validate/{plan_id} ────────────────────────────────────────────

class TestValidateEndpoint:

    def test_validate_200(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        r = client.post(f"/plans/validate/{pid}")
        assert r.status_code == 200

    def test_validate_valid_true(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        r = client.post(f"/plans/validate/{pid}")
        assert r.json()["valid"] is True

    def test_validate_sets_ready(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        r = client.post(f"/plans/validate/{pid}")
        assert r.json()["plan_status"] == "READY"

    def test_validate_paused_mission_fails(self):
        a = _setup_auth(active=False)
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        r = client.post(f"/plans/validate/{pid}")
        assert r.json()["valid"] is False
        assert r.json()["plan_status"] == "DRAFT"

    def test_validate_missing_404(self):
        r = client.post("/plans/validate/no-such-plan")
        assert r.status_code == 404

    def test_validate_records_analytics(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        client.post(f"/plans/validate/{pid}")
        assert client.get("/plans/analytics").json()["plans_validated"] == 1


# ── GET /plans ────────────────────────────────────────────────────────────────

class TestListEndpoint:

    def test_empty(self):
        assert client.get("/plans").json() == []

    def test_list_after_create(self):
        a = _setup_auth()
        client.post(f"/plans/create/{a.authorization_id}")
        assert len(client.get("/plans").json()) == 1

    def test_filter_mission(self):
        a = _setup_auth(mission="m-A")
        client.post(f"/plans/create/{a.authorization_id}")
        assert len(client.get("/plans?mission_id=m-A").json()) == 1

    def test_filter_status_draft(self):
        a = _setup_auth()
        client.post(f"/plans/create/{a.authorization_id}")
        assert len(client.get("/plans?status=DRAFT").json()) == 1

    def test_filter_invalid_status_400(self):
        assert client.get("/plans?status=BOGUS").status_code == 400

    def test_list_omits_steps(self):
        a = _setup_auth()
        client.post(f"/plans/create/{a.authorization_id}")
        assert "steps" not in client.get("/plans").json()[0]


# ── GET /plans/{id}, /mission, /task ──────────────────────────────────────────

class TestGetEndpoints:

    def test_get_by_id(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        r = client.get(f"/plans/{pid}")
        assert r.status_code == 200
        assert r.json()["plan_id"] == pid

    def test_get_by_id_has_steps(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        assert "steps" in client.get(f"/plans/{pid}").json()

    def test_get_missing_404(self):
        assert client.get("/plans/no-such").status_code == 404

    def test_plans_for_mission(self):
        a = _setup_auth(mission="m-X")
        client.post(f"/plans/create/{a.authorization_id}")
        assert len(client.get("/plans/mission/m-X").json()) == 1

    def test_plans_for_task(self):
        a = _setup_auth(task="t-X")
        client.post(f"/plans/create/{a.authorization_id}")
        assert len(client.get("/plans/task/t-X").json()) == 1

    def test_plans_for_unknown_mission_empty(self):
        assert client.get("/plans/mission/absent").json() == []


# ── GET /plans/inspect/{id} ───────────────────────────────────────────────────

class TestInspectEndpoint:

    def test_inspect_200(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        assert client.get(f"/plans/inspect/{pid}").status_code == 200

    def test_inspect_keys(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        j = client.get(f"/plans/inspect/{pid}").json()
        for k in ["plan_id", "plan", "rollback", "validation", "authorization",
                  "mission_context", "analytics", "latency_ms"]:
            assert k in j

    def test_inspect_missing_404(self):
        assert client.get("/plans/inspect/no-such").status_code == 404


# ── POST /plans/{id}/archive ──────────────────────────────────────────────────

class TestArchiveEndpoint:

    def test_archive_200(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        r = client.post(f"/plans/{pid}/archive")
        assert r.status_code == 200
        assert r.json()["status"] == "ABORTED"

    def test_archive_sets_status(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        client.post(f"/plans/{pid}/archive")
        assert client.get(f"/plans/{pid}").json()["status"] == "ABORTED"

    def test_archive_twice_409(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        client.post(f"/plans/{pid}/archive")
        assert client.post(f"/plans/{pid}/archive").status_code == 409

    def test_archive_missing_404(self):
        assert client.post("/plans/no-such/archive").status_code == 404


# ── Full lifecycle: authorization → planner → validator ───────────────────────

class TestFullLifecycle:

    def test_create_validate_ready(self):
        a = _setup_auth()
        create = client.post(f"/plans/create/{a.authorization_id}")
        pid = create.json()["plan_id"]
        validate = client.post(f"/plans/validate/{pid}")
        assert validate.json()["valid"] is True
        final = client.get(f"/plans/{pid}")
        assert final.json()["status"] == "READY"
        assert final.json()["is_ready"] is True

    def test_plan_tied_to_authorization(self):
        a = _setup_auth()
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        plan = plan_reg.get_for_authorization(a.authorization_id)
        assert plan.plan_id == pid


# ── Authorization-only contract (Component 10) ────────────────────────────────

class TestAuthorizationOnlyContract:

    def test_planner_rejects_governance_contract(self):
        from app.execution_planning import planner
        from app.execution_planning.planner import PlannerInputError
        from app.governance.models import make_contract
        c = make_contract(str(uuid.uuid4()), True, "t", time.time(),
                          "TRUST_ENGINE", str(uuid.uuid4()), "HIGH",
                          mission_id="m-1", ttl_seconds=3600)
        with pytest.raises(PlannerInputError):
            planner.create_plan(c)

    def test_create_from_executable_authorization_only(self):
        # Only an ExecutionAuthorization id is accepted by the create endpoint
        a = _setup_auth()
        r = client.post(f"/plans/create/{a.authorization_id}")
        assert r.status_code == 200


# ── Mission integration (V5.0 inspector) ──────────────────────────────────────

class TestMissionIntegration:

    def test_mission_inspect_has_execution_planning(self):
        a = _setup_auth(mission="m-mi")
        client.post(f"/plans/create/{a.authorization_id}")
        r = client.get("/mission/m-mi/inspect")
        assert r.status_code == 200
        assert "execution_planning" in r.json()

    def test_mission_inspect_planning_populated(self):
        a = _setup_auth(mission="m-mi2")
        pid = client.post(f"/plans/create/{a.authorization_id}").json()["plan_id"]
        client.post(f"/plans/validate/{pid}")
        ep = client.get("/mission/m-mi2/inspect").json()["execution_planning"]
        assert ep is not None
        assert ep["total_plans"] >= 1
        assert ep["estimated_steps"] == 3
        assert ep["rollback_available"] is True


# ── Runtime integration (V8.9) ────────────────────────────────────────────────

class TestRuntimeIntegration:

    def test_plan_uses_runtime_url(self):
        a = _setup_auth(mission="m-rt")
        # Seed a runtime session with a live url for this mission
        client.post("/runtime/sync", json={"active_mission_id": "m-rt",
                    "active_tab_id": "tab-1", "last_url": "http://live-page.com"})
        plan = client.post(f"/plans/create/{a.authorization_id}").json()
        nav_step = plan["steps"][0]
        assert nav_step["parameters"]["url"] == "http://live-page.com"
