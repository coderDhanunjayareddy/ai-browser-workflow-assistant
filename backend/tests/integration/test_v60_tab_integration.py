"""
V6.0 Integration Tests — Multi-Tab Coordination Layer (36 tests).

Tests the full tab lifecycle across all components:
  - Mission with multiple tabs
  - Task with multiple tabs
  - Snapshot + restoration flow
  - Inspector flow (mission inspect includes tabs section)
  - Mission Intelligence integration (report includes tab_context)
  - Bootstrap integration (enriched_facts includes tab fields)
  - REST API endpoints
"""
import uuid
import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.tabs import analytics as tab_analytics
import app.tabs.registry as tab_reg
import app.tabs.snapshot as tab_snap

from app.mission.lifecycle import create_mission_obj, attach_task
from app.mission import store as mission_store
from app.unified.models import UnifiedTask, TaskState
from app.unified import store as task_store


# ── Client + fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_all():
    tab_reg._reset_for_testing()
    tab_snap._reset_for_testing()
    tab_analytics._reset_for_testing()
    mission_store._reset_for_testing()
    task_store._reset_for_testing()
    yield
    tab_reg._reset_for_testing()
    tab_snap._reset_for_testing()
    tab_analytics._reset_for_testing()
    mission_store._reset_for_testing()
    task_store._reset_for_testing()


def _mission(title="Buy Laptop"):
    return create_mission_obj(title)


def _task(query="research laptops", state="COMPLETED"):
    t = UnifiedTask(
        task_id=str(uuid.uuid4())[:8],
        conversation_id="c1",
        original_query=query,
        state=TaskState(state),
    )
    task_store.put(t)
    return t


def _reg_tab(tab_id, role="RESEARCH", mission_id=None, task_id=None, url=None):
    from app.tabs.models import BrowserTabRole, BrowserTabState
    return tab_reg.register(
        tab_id=tab_id,
        url=url or f"https://{tab_id}.com",
        title=tab_id,
        role=BrowserTabRole(role),
        state=BrowserTabState.open,
        mission_id=mission_id,
        task_id=task_id,
    )


# ── Mission with multiple tabs ─────────────────────────────────────────────────

class TestMissionWithTabs:
    def test_mission_has_research_tabs(self):
        m = _mission("Buy Laptop")
        _reg_tab("t1", "RESEARCH",   mission_id=m.mission_id)
        _reg_tab("t2", "RESEARCH",   mission_id=m.mission_id)
        _reg_tab("t3", "COMPARISON", mission_id=m.mission_id)

        from app.tabs.mission_tab_map import list_open
        tabs = list_open(m.mission_id)
        assert len(tabs) == 3
        roles = {t.role.value for t in tabs}
        assert "RESEARCH"   in roles
        assert "COMPARISON" in roles

    def test_mission_tab_context_aggregates(self):
        m = _mission()
        _reg_tab("t1", "RESEARCH",  mission_id=m.mission_id)
        _reg_tab("t2", "WORKFLOW",  mission_id=m.mission_id)

        from app.tabs.context import build
        ctx = build(m.mission_id)
        assert ctx.tab_count             == 2
        assert ctx.research_tab_present  is True
        assert ctx.workflow_tab_present  is True

    def test_closing_tab_removes_from_active_count(self):
        m = _mission()
        _reg_tab("t1", mission_id=m.mission_id)
        _reg_tab("t2", mission_id=m.mission_id)
        tab_reg.close("t1")

        from app.tabs.context import build
        ctx = build(m.mission_id)
        assert ctx.tab_count == 1

    def test_four_role_tabs_all_detected(self):
        m = _mission()
        for i, role in enumerate(["PRIMARY", "RESEARCH", "COMPARISON", "WORKFLOW"]):
            _reg_tab(f"t{i}", role, mission_id=m.mission_id)

        from app.tabs.context import build
        ctx = build(m.mission_id)
        assert ctx.tab_count              == 4
        assert ctx.workflow_tab_present   is True
        assert ctx.comparison_tab_present is True
        assert ctx.research_tab_present   is True
        assert ctx.primary_tab is not None


# ── Task with multiple tabs ────────────────────────────────────────────────────

class TestTaskWithTabs:
    def test_task_research_tabs(self):
        t = _task()
        _reg_tab("t1", "RESEARCH", task_id=t.task_id)
        _reg_tab("t2", "RESEARCH", task_id=t.task_id)

        from app.tabs.task_tab_map import list_open
        tabs = list_open(t.task_id)
        assert len(tabs) == 2

    def test_task_and_mission_tab_both_linked(self):
        m = _mission()
        t = _task()
        attach_task(m.mission_id, t.task_id)

        _reg_tab("t1", "RESEARCH",
                 mission_id=m.mission_id, task_id=t.task_id)

        from app.tabs.mission_tab_map import list_open as m_list
        from app.tabs.task_tab_map import list_open as t_list

        assert len(m_list(m.mission_id))  == 1
        assert len(t_list(t.task_id))     == 1

    def test_detach_removes_from_task_map(self):
        t = _task()
        _reg_tab("t1", task_id=t.task_id)

        from app.tabs.task_tab_map import detach, list_open
        detach(t.task_id, "t1")
        assert list_open(t.task_id) == []


# ── Snapshot + restoration ─────────────────────────────────────────────────────

class TestSnapshotAndRestoration:
    def test_snapshot_created_on_register(self):
        from app.tabs.models import BrowserTabRole, BrowserTabState
        tab = tab_reg.register("t1", "https://a.com", "A",
                               BrowserTabRole.research, BrowserTabState.open,
                               mission_id="m1")
        snap_id = tab_snap.create(tab, "tab_registered")
        assert snap_id is not None
        assert tab_snap.count("t1") == 1

    def test_restore_from_snapshot(self):
        from app.tabs.models import BrowserTabRole, BrowserTabState, create_tab
        tab = create_tab("https://a.com", "A", BrowserTabRole.research, tab_id="t1")
        tab.mission_id = "m1"
        tab_snap.create(tab, "tab_registered")

        # Clear registry, then restore
        tab_reg._reset_for_testing()
        assert tab_reg.get("t1") is None

        from app.tabs.restoration import restore_all
        result = restore_all()
        assert result.tabs_restored == 1
        restored = tab_reg.get("t1")
        assert restored is not None
        assert restored.mission_id == "m1"
        from app.tabs.models import BrowserTabState
        assert restored.state == BrowserTabState.background

    def test_closed_tab_not_restored(self):
        from app.tabs.models import BrowserTabRole, BrowserTabState, create_tab
        tab = create_tab("https://a.com", "A", BrowserTabRole.research,
                         state=BrowserTabState.closed, tab_id="t1")
        tab_snap.create(tab, "tab_closed")

        tab_reg._reset_for_testing()
        from app.tabs.restoration import restore_all
        result = restore_all()
        assert result.tabs_restored == 0
        assert result.tabs_skipped  == 1


# ── Inspector flow ────────────────────────────────────────────────────────────

class TestInspectorFlow:
    def test_inspect_mission_includes_tabs(self, client):
        resp = client.post("/mission/", json={"title": "Inspect test"})
        assert resp.status_code == 200
        mission_id = resp.json()["mission_id"]

        # Register tabs via API
        client.post("/tabs/register", json={
            "tab_id": "tab-a", "url": "https://amazon.com",
            "title": "Amazon", "role": "RESEARCH", "mission_id": mission_id,
        })
        client.post("/tabs/register", json={
            "tab_id": "tab-b", "url": "https://flipkart.com",
            "title": "Flipkart", "role": "COMPARISON", "mission_id": mission_id,
        })

        resp = client.get(f"/mission/{mission_id}/inspect")
        assert resp.status_code == 200
        body = resp.json()
        assert "tabs" in body
        assert body["tabs"] is not None
        assert body["tabs"]["tab_count"] == 2

    def test_inspect_mission_tabs_roles_present(self, client):
        resp = client.post("/mission/", json={"title": "Roles test"})
        mission_id = resp.json()["mission_id"]

        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "https://a.com", "title": "A",
            "role": "WORKFLOW", "mission_id": mission_id,
        })

        resp = client.get(f"/mission/{mission_id}/inspect")
        tabs = resp.json()["tabs"]
        assert tabs["workflow_tab_present"] is True


# ── Mission Intelligence integration ──────────────────────────────────────────

class TestMissionIntelligenceWithTabs:
    def test_intelligence_report_includes_tab_context(self, client):
        resp = client.post("/mission/", json={"title": "Intel + tabs test"})
        mission_id = resp.json()["mission_id"]

        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "https://amazon.com", "title": "Amazon",
            "role": "RESEARCH", "mission_id": mission_id,
        })

        resp = client.get(f"/mission/{mission_id}/intelligence?force_refresh=true")
        assert resp.status_code == 200
        body = resp.json()
        assert "tab_context" in body
        # Tab context is populated (even if tab_count == 1)
        assert body["tab_context"]["tab_count"] == 1

    def test_intelligence_tab_context_not_none(self, client):
        resp = client.post("/mission/", json={"title": "Tab ctx test"})
        mission_id = resp.json()["mission_id"]

        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u", "title": "T",
            "role": "RESEARCH", "mission_id": mission_id,
        })
        resp = client.get(f"/mission/{mission_id}/intelligence?force_refresh=true")
        assert resp.json()["tab_context"] is not None


# ── Bootstrap integration ──────────────────────────────────────────────────────

class TestBootstrapWithTabs:
    def test_bootstrap_includes_tab_fields(self):
        m = _mission("Laptop mission")
        t = _task()
        t.research_report = {"summary": "done", "sources": [], "key_findings": []}
        task_store.put(t)
        attach_task(m.mission_id, t.task_id)

        _reg_tab("t1", "RESEARCH",   mission_id=m.mission_id)
        _reg_tab("t2", "COMPARISON", mission_id=m.mission_id)
        _reg_tab("t3", "WORKFLOW",   mission_id=m.mission_id)

        from app.mission.bootstrap import enrich_task_bootstrap
        result = enrich_task_bootstrap(task_id=t.task_id, mission_id=m.mission_id)
        assert result is not None
        ef = result.enriched_facts
        assert "mission_tab_count"            in ef
        assert ef["mission_tab_count"]        == 3
        assert ef["mission_workflow_tab_present"]   is True
        assert ef["mission_comparison_tab_present"] is True
        assert ef["mission_research_tab_present"]   is True

    def test_bootstrap_tab_fields_zero_when_no_tabs(self):
        m = _mission()
        t = _task()
        task_store.put(t)
        attach_task(m.mission_id, t.task_id)

        from app.mission.bootstrap import enrich_task_bootstrap
        result = enrich_task_bootstrap(task_id=t.task_id, mission_id=m.mission_id)
        ef = result.enriched_facts
        assert ef.get("mission_tab_count", 0) == 0


# ── REST API endpoints ─────────────────────────────────────────────────────────

class TestTabRestAPI:
    def test_register_tab(self, client):
        resp = client.post("/tabs/register", json={
            "tab_id": "t1", "url": "https://amazon.com",
            "title": "Amazon", "role": "RESEARCH",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["tab_id"] == "t1"
        assert body["role"]   == "RESEARCH"
        assert body["state"]  == "OPEN"

    def test_register_tab_unknown_role_422(self, client):
        resp = client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u", "title": "T", "role": "BOGUS",
        })
        assert resp.status_code == 422

    def test_get_tab_by_id(self, client):
        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "https://a.com", "title": "A", "role": "RESEARCH",
        })
        resp = client.get("/tabs/t1")
        assert resp.status_code == 200
        assert resp.json()["tab_id"] == "t1"

    def test_get_tab_not_found_404(self, client):
        resp = client.get("/tabs/nonexistent")
        assert resp.status_code == 404

    def test_update_tab_role(self, client):
        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u", "title": "T", "role": "RESEARCH",
        })
        resp = client.post("/tabs/t1/update", json={"role": "COMPARISON"})
        assert resp.status_code == 200
        assert resp.json()["role"] == "COMPARISON"

    def test_close_tab(self, client):
        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u", "title": "T", "role": "REFERENCE",
        })
        resp = client.post("/tabs/t1/close")
        assert resp.status_code == 200
        assert resp.json()["closed"] is True

    def test_list_open_tabs(self, client):
        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u1", "title": "T1", "role": "RESEARCH",
        })
        client.post("/tabs/register", json={
            "tab_id": "t2", "url": "u2", "title": "T2", "role": "COMPARISON",
        })
        resp = client.get("/tabs/")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_list_open_excludes_closed(self, client):
        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u", "title": "T", "role": "RESEARCH",
        })
        client.post("/tabs/t1/close")
        resp = client.get("/tabs/")
        assert len(resp.json()) == 0

    def test_get_tabs_for_mission(self, client):
        resp = client.post("/mission/", json={"title": "Mission tabs test"})
        mid = resp.json()["mission_id"]

        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u1", "title": "T1",
            "role": "RESEARCH", "mission_id": mid,
        })
        client.post("/tabs/register", json={
            "tab_id": "t2", "url": "u2", "title": "T2",
            "role": "COMPARISON", "mission_id": mid,
        })
        resp = client.get(f"/tabs/mission/{mid}")
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_get_tabs_for_task(self, client):
        task = _task()
        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u", "title": "T",
            "role": "WORKFLOW", "task_id": task.task_id,
        })
        resp = client.get(f"/tabs/task/{task.task_id}")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_inspect_tabs_endpoint(self, client):
        resp = client.post("/mission/", json={"title": "Inspect"})
        mid = resp.json()["mission_id"]

        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u", "title": "T",
            "role": "RESEARCH", "mission_id": mid,
        })
        resp = client.get(f"/tabs/inspect/{mid}")
        assert resp.status_code == 200
        body = resp.json()
        assert "tabs"        in body
        assert "tab_context" in body
        assert "intelligence" in body
        assert body["tab_context"]["tab_count"] == 1

    def test_tab_analytics_endpoint(self, client):
        client.post("/tabs/register", json={
            "tab_id": "t1", "url": "u", "title": "T", "role": "RESEARCH",
        })
        resp = client.get("/tabs/analytics")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tabs_created"] >= 1
