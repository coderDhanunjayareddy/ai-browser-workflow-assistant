"""Phase E — Integration tests: REST API + additive mission/diagnostics pointers."""
import time
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.mission import store as mission_store
from app.mission.models import Mission, MissionState

client = TestClient(app)

PAGE = """
<body>
  <header><h1>Shop</h1></header>
  <nav aria-label="Primary"><a href="/home" class="active">Home</a><a href="/p">Products</a></nav>
  <form id="search" role="search"><input type="search" name="q"/></form>
  <form id="signup"><label for="e">Email</label><input id="e" name="e" type="email" required/>
    <input name="pw" type="password"/><button type="submit">Join</button></form>
  <table id="t"><caption>Items</caption><thead><tr><th>Name</th></tr></thead>
    <tbody><tr><td>A</td></tr><tr><td>B</td></tr></tbody></table>
  <div role="dialog" aria-label="Confirm"><button>Yes</button><button>No</button></div>
  <footer>F</footer>
</body>
"""


class TestAnalyzeEndpoint:
    def test_analyze_html_200(self):
        r = client.post("/website-intelligence/analyze", json={"html": PAGE, "url": "http://x", "title": "Shop"})
        assert r.status_code == 200

    def test_analyze_full_shape(self):
        j = client.post("/website-intelligence/analyze", json={"html": PAGE}).json()
        for k in ["url", "title", "page", "forms", "tables", "navigation", "dialogs",
                  "registry", "hints", "stats", "latency_ms"]:
            assert k in j

    def test_analyze_detects(self):
        j = client.post("/website-intelligence/analyze", json={"html": PAGE}).json()
        assert len(j["forms"]) == 2
        assert len(j["tables"]) == 1
        assert len(j["dialogs"]) == 1
        assert j["tables"][0]["headers"] == ["Name"]
        assert j["navigation"]["active_page"] == "Home"

    def test_analyze_registry(self):
        j = client.post("/website-intelligence/analyze", json={"html": PAGE}).json()
        assert len(j["registry"]) >= 6
        assert all("semantic_id" in e and "locator" in e for e in j["registry"])

    def test_analyze_snapshot(self):
        snap = {"tag": "body", "children": [{"tag": "form", "id": "f", "children": [{"tag": "input", "name": "q"}]}]}
        j = client.post("/website-intelligence/analyze", json={"snapshot": snap}).json()
        assert len(j["forms"]) == 1

    def test_analyze_missing_input_400(self):
        assert client.post("/website-intelligence/analyze", json={}).status_code == 400

    def test_page_tree_semantic(self):
        j = client.post("/website-intelligence/analyze", json={"html": PAGE}).json()
        types = {c["type"] for c in j["page"]["root"]["children"]}
        assert "HEADER" in types and "NAVIGATION" in types and "FORM" in types and "FOOTER" in types


class TestLiveEndpoints:
    def test_live_404_no_session(self):
        assert client.get("/website-intelligence/live/no-such-exec").status_code == 404

    def test_live_section_bad_section_404_or_400(self):
        # no session → 404 (session check happens before section validation in our impl? both acceptable)
        r = client.get("/website-intelligence/live/no-such/forms")
        assert r.status_code in (400, 404)

    def test_live_section_invalid_name(self):
        # invalid section name path still 404 because no session; ensure route exists
        assert client.get("/website-intelligence/live/x/bogus").status_code in (400, 404)


class TestMissionPointer:
    def test_mission_inspect_has_website_intelligence(self):
        mission_store.put(Mission("m-wi", "WI Test", "obj", MissionState.active))
        r = client.get("/mission/m-wi/inspect")
        assert r.status_code == 200
        assert "website_intelligence" in r.json()
        wi = r.json()["website_intelligence"]
        assert wi is not None
        assert "available" in wi and "analyze_endpoint" in wi


class TestDiagnosticsPointer:
    def test_diagnostics_has_website_intelligence(self):
        # create a Phase D execution so diagnostics has data, then check the pointer
        from app.execution_gateway import engine as gateway, registry as ereg, analytics as ganal, timeline as gtl, audit
        from app.execution_gateway.models import RetryConfig, ExecutionState
        from app.execution_gateway.browser.playwright_adapter import PlaywrightAdapter
        from app.execution_gateway.browser import monitor as mon, metrics as met, exec_timeline as etl
        from app.execution_planning import registry as plan_reg, planner
        from app.execution_planning.registry import set_status
        from app.execution_planning.models import PlanStatus
        from app.authorization import registry as auth_reg
        from app.authorization.models import make_authorization

        for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mon, met, etl]:
            m._reset_for_testing()
        mission_store.put(Mission("m-diag-wi", "t", "objective satisfied", MissionState.active, task_ids=["t-1"]))
        auth = make_authorization("c", True, "ok", "HIGH", time.time() + 3600, mission_id="m-diag-wi", task_id="t-1")
        auth_reg.add(auth)
        plan = planner.create_plan(auth); plan_reg.add(plan); set_status(plan.plan_id, PlanStatus.ready)

        class FakeLoc:
            def __init__(self, p): self.p = p
            def click(self, **k): pass
            def fill(self, t, **k): pass
            def inner_text(self): return "objective satisfied"
            def count(self): return 1
        class FakePage:
            url = "about:blank"; body = "objective satisfied"
            def is_closed(self): return False
            def goto(self, u, **k): pass
            def title(self): return "T"
            def locator(self, s): return FakeLoc(self)
            def get_by_test_id(self, v): return FakeLoc(self)
            def get_by_label(self, v): return FakeLoc(self)
            def get_by_role(self, v, name=None): return FakeLoc(self)
            def get_by_placeholder(self, v): return FakeLoc(self)
            def get_by_text(self, v): return FakeLoc(self)
            def inner_text(self, sel): return "objective satisfied"
            def content(self): return "<html>objective satisfied</html>"
            def wait_for_timeout(self, ms): pass
        class FakeSession:
            def __init__(self): self.page = FakePage(); self.active_tab_id = "tab-0"; self.downloads = []; self.context = None
            def ensure_page(self): return self.page
            def screenshot(self, l=""): return None
        class FakeMgr:
            def __init__(self): self.s = FakeSession()
            def get_or_create(self, e, headless=True): return self.s
            def get(self, e): return self.s
            def close(self, e): return True

        adapter = PlaywrightAdapter(session_manager=FakeMgr(), adaptive=True, recovery=True, post_validation=True)
        rec = gateway.start(plan.plan_id, auto_run=False, adapter=adapter, retry_config=RetryConfig(max_retries=0))
        adapter.execution_id = rec.execution_id
        gateway.resume(rec.execution_id, adapter=adapter)
        d = client.get(f"/gateway/browser/diagnostics/{rec.execution_id}").json()
        assert "website_intelligence" in d
        assert "live_endpoint" in d["website_intelligence"]
        for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mon, met, etl]:
            m._reset_for_testing()
