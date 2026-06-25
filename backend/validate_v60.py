"""
V6.0 Multi-Tab Coordination Layer — Validation Suite.

138 deterministic checks across all 14 components.
Run with: python validate_v60.py
Requires no DB. No LLM. Pure in-memory.
"""
import sys
import importlib
import traceback
from datetime import datetime, timedelta

_PASS = 0
_FAIL = 0


def check(label: str, condition: bool) -> None:
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  [OK]  {label}")
    else:
        _FAIL += 1
        print(f"  [FAIL] {label}")


def section(title: str) -> None:
    print(f"\n== {title} ==")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_all():
    import app.tabs.registry as r
    import app.tabs.snapshot as s
    from app.tabs import analytics as a
    r._reset_for_testing()
    s._reset_for_testing()
    a._reset_for_testing()


def _reg(tab_id, role_str="RESEARCH", mission_id=None, task_id=None, url=None,
         state_str="OPEN"):
    from app.tabs import registry as reg
    from app.tabs.models import BrowserTabRole, BrowserTabState
    return reg.register(
        tab_id     = tab_id,
        url        = url or f"https://{tab_id}.com",
        title      = tab_id,
        role       = BrowserTabRole(role_str),
        state      = BrowserTabState(state_str),
        mission_id = mission_id,
        task_id    = task_id,
    )


def _snap(tab, trigger="tab_registered"):
    from app.tabs import snapshot as snap
    return snap.create(tab, trigger)


# ── 1. Package Structure ──────────────────────────────────────────────────────

section("1. Package Structure")
for mod in [
    "app.tabs",
    "app.tabs.models",
    "app.tabs.registry",
    "app.tabs.mission_tab_map",
    "app.tabs.task_tab_map",
    "app.tabs.snapshot",
    "app.tabs.restoration",
    "app.tabs.context",
    "app.tabs.intelligence",
    "app.tabs.analytics",
    "app.schemas.tabs",
    "app.api.routes.tabs",
]:
    try:
        importlib.import_module(mod)
        check(f"Import {mod}", True)
    except Exception as e:
        check(f"Import {mod}: {e}", False)


# ── 2. Tab Domain Models ──────────────────────────────────────────────────────

section("2. Tab Domain Models")
from app.tabs.models import (
    BrowserTab, BrowserTabState, BrowserTabRole,
    TabSyncPayload, create_tab,
    ACTIVE_TAB_STATES, TERMINAL_TAB_STATES,
)

check("BrowserTabState has 4 values",  len(BrowserTabState) == 4)
check("BrowserTabRole  has 5 values",  len(BrowserTabRole)  == 5)
check("OPEN  in ACTIVE_TAB_STATES",   BrowserTabState.open       in ACTIVE_TAB_STATES)
check("ACTIVE in ACTIVE_TAB_STATES",  BrowserTabState.active     in ACTIVE_TAB_STATES)
check("BACKGROUND in ACTIVE_TAB_STATES", BrowserTabState.background in ACTIVE_TAB_STATES)
check("CLOSED in TERMINAL_TAB_STATES", BrowserTabState.closed    in TERMINAL_TAB_STATES)
check("CLOSED NOT in ACTIVE_TAB_STATES", BrowserTabState.closed  not in ACTIVE_TAB_STATES)

t = create_tab("https://amazon.com", "Amazon", BrowserTabRole.research, tab_id="t-test")
check("create_tab returns BrowserTab",  isinstance(t, BrowserTab))
check("create_tab sets url",            t.url   == "https://amazon.com")
check("create_tab sets role",           t.role  == BrowserTabRole.research)
check("create_tab sets state OPEN",     t.state == BrowserTabState.open)
check("BrowserTab.is_active True when OPEN", t.is_active is True)
check("to_summary returns dict",        isinstance(t.to_summary(), dict))
check("to_summary has tab_id",          "tab_id" in t.to_summary())
check("to_summary has role as value",   t.to_summary()["role"] == "RESEARCH")

t.state = BrowserTabState.closed
check("is_active False when CLOSED", t.is_active is False)
check("is_closed True when CLOSED",  t.is_closed is True)

sp = TabSyncPayload(tab_id="x", url="https://a.com", title="A")
check("TabSyncPayload construction", sp.tab_id == "x")
check("TabSyncPayload to_dict",      isinstance(sp.to_dict(), dict))
check("TabSyncPayload has timestamp", "timestamp" in sp.to_dict())


# ── 3. Tab Registry ───────────────────────────────────────────────────────────

section("3. Tab Registry")
_reset_all()
import app.tabs.registry as tab_reg

t1 = _reg("r1", "RESEARCH", mission_id="m1")
check("Register returns BrowserTab",     isinstance(t1, BrowserTab))
check("Registry count == 1",            tab_reg.count() == 1)
check("get() by tab_id",                tab_reg.get("r1") is not None)
check("all_open() includes open tab",   any(t.tab_id == "r1" for t in tab_reg.all_open()))

_reg("r2", "COMPARISON", mission_id="m1")
_reg("r3", "WORKFLOW",   mission_id="m2")
check("count == 3",                     tab_reg.count() == 3)
check("open_for_mission m1 == 2",       len(tab_reg.open_for_mission("m1")) == 2)
check("open_for_mission m2 == 1",       len(tab_reg.open_for_mission("m2")) == 1)

tab_reg.close("r1")
check("close marks CLOSED",             tab_reg.get("r1").state == BrowserTabState.closed)
check("all_open excludes closed",       not any(t.tab_id == "r1" for t in tab_reg.all_open()))
check("count_open == 2 after close",    tab_reg.count_open() == 2)

_reg("r4", "RESEARCH", mission_id="m1")
tab_reg.set_active("r4")
check("set_active marks tab ACTIVE",    tab_reg.get("r4").state == BrowserTabState.active)

tab_reg.attach_mission("r3", "m1")
check("attach_mission updates mission_id", tab_reg.get("r3").mission_id == "m1")

tab_reg.attach_task("r2", "task-99")
check("attach_task updates task_id",    tab_reg.get("r2").task_id == "task-99")

updated = tab_reg.update("r2", role=BrowserTabRole.primary)
check("update() changes role",          updated.role == BrowserTabRole.primary)

detached = tab_reg.detach_mission("r3")
check("detach_mission clears mission_id", tab_reg.get("r3").mission_id is None)

check("get() None for unknown",         tab_reg.get("nonexistent") is None)


# ── 4. Mission Tab Map ────────────────────────────────────────────────────────

section("4. Mission Tab Map")
_reset_all()
import app.tabs.mission_tab_map as mtm

_reg("m1-t1", "RESEARCH",   mission_id="m1")
_reg("m1-t2", "COMPARISON", mission_id="m1")
_reg("m1-t3", "PRIMARY",    mission_id="m1")
_reg("m2-t1", "RESEARCH",   mission_id="m2")

check("list_open m1 == 3",             len(mtm.list_open("m1")) == 3)
check("list_open m2 == 1",             len(mtm.list_open("m2")) == 1)
check("list_open m99 empty",           mtm.list_open("m99") == [])

prim = mtm.primary_tab("m1")
check("primary_tab returns PRIMARY",   prim is not None and prim.role == BrowserTabRole.primary)

check("count m1 == 3",                 mtm.count("m1") == 3)
check("summary returns list",          isinstance(mtm.summary("m1"), list))
check("summary contains dicts",       all(isinstance(x, dict) for x in mtm.summary("m1")))

by_role = mtm.by_role("m1", BrowserTabRole.research)
check("by_role RESEARCH returns 1",    len(by_role) == 1)

mtm.attach("m1", "m2-t1")
check("attach links tab to mission",   tab_reg.get("m2-t1").mission_id == "m1")

mtm.detach("m1", "m2-t1")
check("detach removes mission link",   tab_reg.get("m2-t1").mission_id is None)

tab_reg.close("m1-t1")
check("list_open excludes closed",     len(mtm.list_open("m1")) == 2)


# ── 5. Task Tab Map ───────────────────────────────────────────────────────────

section("5. Task Tab Map")
_reset_all()
import app.tabs.task_tab_map as ttm

_reg("tt1", "RESEARCH",   task_id="task-A")
_reg("tt2", "WORKFLOW",   task_id="task-A")
_reg("tt3", "REFERENCE",  task_id="task-B")

check("list_open task-A == 2",         len(ttm.list_open("task-A")) == 2)
check("list_open task-B == 1",         len(ttm.list_open("task-B")) == 1)
check("list_open unknown empty",        ttm.list_open("task-X") == [])
check("count task-A == 2",             ttm.count("task-A") == 2)

ttm.attach("task-A", "tt3")
check("attach adds tab to task",        tab_reg.get("tt3").task_id == "task-A")

ttm.detach("task-A", "tt3")
check("detach removes task link",       tab_reg.get("tt3").task_id is None)

tab_reg.close("tt1")
check("list_open excludes closed",      len(ttm.list_open("task-A")) == 1)


# ── 6. Tab Snapshot Manager ───────────────────────────────────────────────────

section("6. Tab Snapshot Manager")
_reset_all()
import app.tabs.snapshot as snap

tab = create_tab("https://a.com", "A", BrowserTabRole.research, tab_id="snap-t1")

sid1 = snap.create(tab, "tab_registered")
check("create returns snapshot_id",     sid1 is not None)
check("count == 1 after create",        snap.count("snap-t1") == 1)

sid2 = snap.create(tab, "mission_linked")
check("second create returns id",       sid2 is not None)
check("count == 2 after 2 creates",     snap.count("snap-t1") == 2)
check("ids are different",              sid1 != sid2)

latest = snap.load_latest("snap-t1")
check("load_latest returns dict",       isinstance(latest, dict))
check("load_latest has tab_id",         latest.get("tab_id") == "snap-t1")
check("load_latest has trigger",        "trigger" in latest)
check("load_latest newest first",       latest["trigger"] == "mission_linked")

all_snaps = snap.load_all("snap-t1")
check("load_all returns 2",             len(all_snaps) == 2)

bad = snap.create(tab, "INVALID_TRIGGER")
check("invalid trigger returns None",   bad is None)
check("count unchanged after invalid",  snap.count("snap-t1") == 2)

check("all_tab_ids includes snap-t1",   "snap-t1" in snap.all_tab_ids())

from app.tabs import analytics as tab_a
tab_a._reset_for_testing()
snap._reset_for_testing()
snap.create(tab, "tab_closed")
check("reset clears store",             snap.count("snap-t1") == 1)
check("snapshot recorded in analytics", tab_a.get_analytics()["tab_snapshots"] == 1)


# ── 7. Tab Restoration ────────────────────────────────────────────────────────

section("7. Tab Restoration")
_reset_all()
from app.tabs.restoration import TabRestorationService, restore_all, warmup

# Snapshot a tab
tab_open   = create_tab("https://open.com",   "Open",   BrowserTabRole.research,   tab_id="res-1")
tab_closed = create_tab("https://closed.com", "Closed", BrowserTabRole.reference,
                        state=BrowserTabState.closed, tab_id="res-2")
tab_miss   = create_tab("https://miss.com",   "Miss",   BrowserTabRole.comparison, tab_id="res-3")
tab_miss.mission_id = "m-restore"

snap.create(tab_open,   "tab_registered")
snap.create(tab_closed, "tab_closed")
snap.create(tab_miss,   "mission_linked")

# Clear registry then restore
tab_reg._reset_for_testing()
tab_a._reset_for_testing()

svc = TabRestorationService()
result = svc.restore_all()
check("restore_all success",             result.success is True)
check("tabs_restored == 2",              result.tabs_restored == 2)
check("tabs_skipped  == 1",              result.tabs_skipped  == 1)
check("mission_links == 1",              result.mission_links == 1)
check("errors == []",                    result.errors == [])

restored = tab_reg.get("res-1")
check("res-1 in registry",               restored is not None)
check("restored as BACKGROUND",          restored.state == BrowserTabState.background)

check("res-2 not in registry",           tab_reg.get("res-2") is None)

miss_tab = tab_reg.get("res-3")
check("res-3 in registry",               miss_tab is not None)
check("mission_id restored",             miss_tab.mission_id == "m-restore")

check("analytics tabs_restored == 2",    tab_a.get_analytics()["tabs_restored"] == 2)

# warmup callable
_reset_all()
n = warmup()
check("warmup returns int",              isinstance(n, int))


# ── 8. Cross Tab Context ──────────────────────────────────────────────────────

section("8. Cross Tab Context")
_reset_all()
from app.tabs.context import CrossTabContextBuilder, build as build_ctx

check("empty mission => tab_count 0",    build_ctx("empty-m").tab_count == 0)
check("empty mission => no duplicates",  build_ctx("empty-m").duplicate_urls == [])

_reg("ctx-1", "RESEARCH",   mission_id="ctx-m")
_reg("ctx-2", "COMPARISON", mission_id="ctx-m")
_reg("ctx-3", "WORKFLOW",   mission_id="ctx-m")
_reg("ctx-4", "PRIMARY",    mission_id="ctx-m")
_reg("other", "RESEARCH",   mission_id="other-m")

ctx = build_ctx("ctx-m")
check("tab_count == 4",                  ctx.tab_count == 4)
check("workflow_tab_present True",       ctx.workflow_tab_present   is True)
check("comparison_tab_present True",     ctx.comparison_tab_present is True)
check("research_tab_present True",       ctx.research_tab_present   is True)
check("primary_tab not None",            ctx.primary_tab is not None)
check("primary_tab role PRIMARY",        ctx.primary_tab["role"] == "PRIMARY")
check("roles_present has 4 roles",       len(ctx.roles_present) == 4)
check("to_dict serializable",            "tab_count" in ctx.to_dict())

# Duplicate URL detection
_reset_all()
_reg("dup1", url="https://amazon.com", mission_id="dup-m")
_reg("dup2", url="https://amazon.com", mission_id="dup-m")
ctx_dup = build_ctx("dup-m")
check("duplicate_urls detected",         "https://amazon.com" in ctx_dup.duplicate_urls)

# Active tab
_reset_all()
_reg("act1", state_str="ACTIVE",     mission_id="act-m")
_reg("act2", state_str="BACKGROUND", mission_id="act-m")
ctx_act = build_ctx("act-m")
check("active_tab_count == 1",          ctx_act.active_tab_count == 1)
check("active_tab identified",          ctx_act.active_tab is not None)
check("active_tab tab_id correct",      ctx_act.active_tab["tab_id"] == "act1")


# ── 9. Tab Intelligence ───────────────────────────────────────────────────────

section("9. Tab Intelligence")
_reset_all()
from app.tabs.intelligence import (
    TabIntelligenceAnalyzer, TabFindingSeverity, TabFinding,
    analyze as intel_analyze,
)
from app.tabs.context import TabContext

def _make_ctx(summaries, dup_urls=None, mission_id="m1"):
    wf = any(t["role"] == "WORKFLOW"   for t in summaries)
    cp = any(t["role"] == "COMPARISON" for t in summaries)
    rs = any(t["role"] == "RESEARCH"   for t in summaries)
    return TabContext(
        mission_id=mission_id, tab_count=len(summaries),
        active_tab_count=0, tab_summaries=summaries,
        roles_present=list({t["role"] for t in summaries}),
        primary_tab=None, active_tab=None,
        workflow_tab_present=wf, comparison_tab_present=cp, research_tab_present=rs,
        duplicate_urls=dup_urls or [], latency_ms=0,
    )

def _ts(tid, role="RESEARCH", state="OPEN", mission_id="m1", url=None, updated_at=None):
    return {
        "tab_id": tid, "url": url or f"https://{tid}.com", "title": tid,
        "role": role, "state": state, "mission_id": mission_id, "task_id": None,
        "updated_at": (updated_at or datetime.utcnow()).isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    }

empty_result = intel_analyze(_make_ctx([]))
check("Empty tabs => no findings",        empty_result.findings  == [])
check("Empty tabs => has_issues False",   empty_result.has_issues is False)

two_research = _make_ctx([_ts("t1", "RESEARCH"), _ts("t2", "RESEARCH")])
r2 = intel_analyze(two_research)
codes = {f.code for f in r2.findings}
check("2 research => MISSING_COMPARISON_TAB",  "MISSING_COMPARISON_TAB" in codes)
check("MISSING_COMPARISON_TAB is WARNING",
    next(f for f in r2.findings if f.code == "MISSING_COMPARISON_TAB").severity
    == TabFindingSeverity.warning)

with_comp = _make_ctx([_ts("t1", "RESEARCH"), _ts("t2", "RESEARCH"), _ts("t3", "COMPARISON")])
check("2 research + comparison => no MISSING_COMPARISON_TAB",
    "MISSING_COMPARISON_TAB" not in {f.code for f in intel_analyze(with_comp).findings})

ready_ctx = _make_ctx([_ts("t1", "RESEARCH")])
r_ready = intel_analyze(ready_ctx, readiness_score=0.90)
check("High readiness no workflow => MISSING_WORKFLOW_TAB",
    "MISSING_WORKFLOW_TAB" in {f.code for f in r_ready.findings})

low_ready = intel_analyze(ready_ctx, readiness_score=0.50)
check("Low readiness no workflow => no MISSING_WORKFLOW_TAB",
    "MISSING_WORKFLOW_TAB" not in {f.code for f in low_ready.findings})

dup_ctx = _make_ctx(
    [_ts("t1", url="https://amazon.com"), _ts("t2", url="https://amazon.com")],
    dup_urls=["https://amazon.com"]
)
check("Duplicate URL => DUPLICATE_TABS",
    "DUPLICATE_TABS" in {f.code for f in intel_analyze(dup_ctx).findings})

stale_time = datetime.utcnow() - timedelta(minutes=35)
stale_ctx = _make_ctx([_ts("t1", state="BACKGROUND", updated_at=stale_time)])
check("Stale BACKGROUND => STALE_TABS",
    "STALE_TABS" in {f.code for f in intel_analyze(stale_ctx).findings})

orphan_ts = {**_ts("t1"), "mission_id": None}
orphan_ctx = _make_ctx([orphan_ts])
check("No mission_id => ORPHAN_TABS",
    "ORPHAN_TABS" in {f.code for f in intel_analyze(orphan_ctx).findings})

r_recs = intel_analyze(two_research)
check("recommendations generated for findings", len(r_recs.recommendations) > 0)
check("to_dict has findings key",              "findings" in r_recs.to_dict())
check("to_dict has recommendations key",       "recommendations" in r_recs.to_dict())


# ── 10. Tab Analytics ─────────────────────────────────────────────────────────

section("10. Tab Analytics")
from app.tabs import analytics as tab_an
tab_an._reset_for_testing()

a0 = tab_an.get_analytics()
check("All counters start at 0",   all(v == 0 for v in a0.values()))
check("active_tabs starts at 0",   a0["active_tabs"] == 0)

tab_an.record_tab_created()
tab_an.record_tab_created()
tab_an.record_tab_closed()
a1 = tab_an.get_analytics()
check("tabs_created == 2",         a1["tabs_created"] == 2)
check("tabs_closed == 1",          a1["tabs_closed"]  == 1)
check("active_tabs == 1",          a1["active_tabs"]  == 1)

tab_an.record_tab_restored()
check("tabs_restored == 1",        tab_an.get_analytics()["tabs_restored"] == 1)

tab_an.record_snapshot()
check("tab_snapshots == 1",        tab_an.get_analytics()["tab_snapshots"] == 1)

tab_an.record_mission_link()
check("mission_tab_links == 1",    tab_an.get_analytics()["mission_tab_links"] == 1)

tab_an.record_task_link()
check("task_tab_links == 1",       tab_an.get_analytics()["task_tab_links"] == 1)

tab_an.record_context_build(latency_ms=8)
tab_an.record_context_build(latency_ms=12)
a2 = tab_an.get_analytics()
check("context_builds == 2",       a2["context_builds"] == 2)
check("avg_latency_ms == 10",      a2["avg_latency_ms"] == 10)

tab_an.record_intelligence_run()
check("intelligence_runs == 1",    tab_an.get_analytics()["intelligence_runs"] == 1)

# active_tabs never negative
tab_an._reset_for_testing()
tab_an.record_tab_closed()
check("active_tabs >= 0 always",   tab_an.get_analytics()["active_tabs"] == 0)


# ── 11. Extension Contract ────────────────────────────────────────────────────

section("11. Extension Contract (V6.5 prep)")
sp = TabSyncPayload(tab_id="ext-1", url="https://amazon.com", title="Amazon",
                    active=True, mission_id="m1")
check("TabSyncPayload has tab_id",     sp.tab_id  == "ext-1")
check("TabSyncPayload has url",        sp.url     == "https://amazon.com")
check("TabSyncPayload has active",     sp.active  is True)
check("TabSyncPayload has mission_id", sp.mission_id == "m1")
check("to_dict includes all keys",
    {"tab_id","url","title","active","mission_id","task_id","timestamp"}
    == set(sp.to_dict().keys()))
check("task_id defaults None",         sp.task_id is None)


# ── 12. Mission Intelligence Integration ──────────────────────────────────────

section("12. Mission Intelligence Integration")
_reset_all()
from app.mission.intelligence.models import MissionIntelligenceReport
check("MissionIntelligenceReport has tab_context field",
    hasattr(MissionIntelligenceReport, "__dataclass_fields__")
    and "tab_context" in MissionIntelligenceReport.__dataclass_fields__)

# Build a full intelligence report with tab context populated
_reg("mi-t1", "RESEARCH",   mission_id="mi-m1")
_reg("mi-t2", "COMPARISON", mission_id="mi-m1")
ctx_for_mi = build_ctx("mi-m1")
check("context built for mi-m1",       ctx_for_mi.tab_count == 2)
check("tab_count in to_dict",          ctx_for_mi.to_dict()["tab_count"] == 2)
check("comparison_tab_present",        ctx_for_mi.comparison_tab_present is True)


# ── 13. Bootstrap Integration ─────────────────────────────────────────────────

section("13. Bootstrap Integration")
_reset_all()
try:
    from app.mission.bootstrap import enrich_task_bootstrap
    import uuid
    from app.unified.models import UnifiedTask, TaskState
    from app.mission.lifecycle import create_mission_obj, attach_task
    from app.unified import store as task_store
    from app.mission import store as mission_store

    task_store._reset_for_testing()
    mission_store._reset_for_testing()

    m = create_mission_obj("V6.0 bootstrap test")
    t = UnifiedTask(
        task_id=str(uuid.uuid4())[:8],
        conversation_id="c1",
        original_query="buy laptop",
        state=TaskState.completed,
    )
    task_store.put(t)
    attach_task(m.mission_id, t.task_id)

    _reg("boot-1", "RESEARCH",   mission_id=m.mission_id)
    _reg("boot-2", "COMPARISON", mission_id=m.mission_id)
    _reg("boot-3", "WORKFLOW",   mission_id=m.mission_id)

    result = enrich_task_bootstrap(task_id=t.task_id, mission_id=m.mission_id)
    ef = result.enriched_facts if result else {}

    check("Bootstrap returns result",              result is not None)
    check("mission_tab_count == 3",                ef.get("mission_tab_count") == 3)
    check("mission_research_tab_present True",     ef.get("mission_research_tab_present")   is True)
    check("mission_comparison_tab_present True",   ef.get("mission_comparison_tab_present") is True)
    check("mission_workflow_tab_present True",     ef.get("mission_workflow_tab_present")   is True)

except Exception as e:
    check(f"Bootstrap integration OK: {e}", False)


# ── 14. REST API & Inspector ──────────────────────────────────────────────────

section("14. REST API & Inspector")
try:
    from fastapi.testclient import TestClient
    from app.main import app
    _reset_all()
    try:
        from app.mission import store as ms
        from app.unified import store as us
        ms._reset_for_testing()
        us._reset_for_testing()
    except Exception:
        pass

    client = TestClient(app)

    # POST /tabs/register
    resp = client.post("/tabs/register", json={
        "tab_id": "api-t1", "url": "https://amazon.com",
        "title": "Amazon", "role": "RESEARCH",
    })
    check("POST /tabs/register 200",         resp.status_code == 200)
    body = resp.json()
    check("register returns tab_id",         body.get("tab_id") == "api-t1")
    check("register returns role=RESEARCH",  body.get("role")   == "RESEARCH")
    check("register returns state=OPEN",     body.get("state")  == "OPEN")

    # POST /tabs/register (invalid role)
    resp422 = client.post("/tabs/register", json={
        "tab_id": "bad", "url": "u", "title": "T", "role": "BOGUS",
    })
    check("Unknown role => 422",             resp422.status_code == 422)

    # GET /tabs/
    resp = client.get("/tabs/")
    check("GET /tabs/ 200",                  resp.status_code == 200)
    check("GET /tabs/ returns list",         isinstance(resp.json(), list))
    check("GET /tabs/ has 1 tab",            len(resp.json()) == 1)

    # GET /tabs/{tab_id}
    resp = client.get("/tabs/api-t1")
    check("GET /tabs/{id} 200",              resp.status_code == 200)
    check("GET /tabs/{id} correct tab",      resp.json().get("tab_id") == "api-t1")

    # GET /tabs/{unknown}
    check("GET /tabs/unknown 404",           client.get("/tabs/nope").status_code == 404)

    # POST /tabs/{tab_id}/update
    resp = client.post("/tabs/api-t1/update", json={"role": "COMPARISON"})
    check("POST update 200",                 resp.status_code == 200)
    check("update returns new role",         resp.json().get("role") == "COMPARISON")

    # POST /tabs/{tab_id}/close
    resp = client.post("/tabs/api-t1/close")
    check("POST close 200",                  resp.status_code == 200)
    check("close returns closed=true",       resp.json().get("closed") is True)

    # GET /tabs/analytics
    resp = client.get("/tabs/analytics")
    check("GET /tabs/analytics 200",         resp.status_code == 200)
    check("analytics has tabs_created",      "tabs_created" in resp.json())

    # Mission-scoped tab list
    resp_m = client.post("/mission/", json={"title": "Validate mission"})
    mid = resp_m.json()["mission_id"]
    client.post("/tabs/register", json={
        "tab_id": "api-m1", "url": "u1", "title": "T1",
        "role": "RESEARCH", "mission_id": mid,
    })
    client.post("/tabs/register", json={
        "tab_id": "api-m2", "url": "u2", "title": "T2",
        "role": "WORKFLOW", "mission_id": mid,
    })
    resp = client.get(f"/tabs/mission/{mid}")
    check("GET /tabs/mission/{id} 200",      resp.status_code == 200)
    check("Mission tab list has 2 tabs",     len(resp.json()) == 2)

    # Inspector endpoint
    resp = client.get(f"/tabs/inspect/{mid}")
    check("GET /tabs/inspect/{id} 200",      resp.status_code == 200)
    insp = resp.json()
    check("inspect has tabs key",            "tabs" in insp)
    check("inspect has tab_context key",     "tab_context" in insp)
    check("inspect has intelligence key",    "intelligence" in insp)
    check("inspect tab_count == 2",          insp["tab_context"]["tab_count"] == 2)

    # Mission inspect includes tabs section
    resp = client.get(f"/mission/{mid}/inspect")
    check("Mission inspect 200",             resp.status_code == 200)
    mi = resp.json()
    check("Mission inspect has tabs key",    "tabs" in mi)
    check("Mission tabs not None",           mi.get("tabs") is not None)
    check("Mission tabs tab_count == 2",     mi["tabs"].get("tab_count") == 2)

except Exception as e:
    traceback.print_exc()
    check(f"REST API / Inspector: {e}", False)


# ── Final Summary ─────────────────────────────────────────────────────────────

total = _PASS + _FAIL
print(f"\n{'='*60}")
print(f"V6.0 Validation: {_PASS}/{total} checks passed")
if _FAIL:
    print(f"FAILURES: {_FAIL}")
    sys.exit(1)
else:
    print("ALL CHECKS PASSED")
    sys.exit(0)
