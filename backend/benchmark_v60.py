"""
V6.0 Multi-Tab Coordination Layer — Benchmarks.

Measures p95 latency for all coordination components.
Run with: python benchmark_v60.py

Performance targets:
  tab registration (single)       < 2ms  p95
  tab update                      < 1ms  p95
  tab close                       < 1ms  p95
  mission_tab_map.list_open()     < 1ms  p95
  task_tab_map.list_open()        < 1ms  p95
  snapshot.create()               < 1ms  p95
  snapshot.load_latest()          < 0.5ms p95
  restoration (5 tabs)            < 20ms p95
  context.build() (0 tabs)        < 1ms  p95
  context.build() (5 tabs)        < 5ms  p95
  context.build() (20 tabs)       < 10ms p95
  intelligence.analyze() (0 tabs) < 1ms  p95
  intelligence.analyze() (5 tabs) < 2ms  p95
  analytics.get_analytics()       < 0.1ms p95
  API GET /tabs/                  < 10ms p95
  API POST /tabs/register         < 10ms p95
  API GET /tabs/mission/{id}      < 10ms p95
  API GET /tabs/inspect/{id}      < 25ms p95
  API GET /tabs/analytics         < 10ms p95
"""
import time
import statistics
import uuid
from datetime import datetime

REPS = 200


def bench(label: str, fn, reps: int = REPS, target_ms: float = None) -> float:
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    status = ""
    if target_ms is not None:
        status = "OK" if p95 <= target_ms else "SLOW"
    print(f"  {label:<52}  p50={p50:6.3f}ms  p95={p95:6.3f}ms  {status}")
    return p95


def section(title: str) -> None:
    print(f"\n-- {title} --")


# ── Imports & reset helpers ───────────────────────────────────────────────────

import app.tabs.registry as tab_reg
import app.tabs.snapshot as tab_snap
from app.tabs import analytics as tab_an
from app.tabs.models import BrowserTabRole, BrowserTabState, create_tab
from app.tabs.context import build as build_ctx
from app.tabs.intelligence import analyze as intel_analyze
from app.tabs.context import TabContext


def _reset():
    tab_reg._reset_for_testing()
    tab_snap._reset_for_testing()
    tab_an._reset_for_testing()


def _reg(tab_id, role_str="RESEARCH", mission_id=None, task_id=None):
    return tab_reg.register(
        tab_id=tab_id,
        url=f"https://{tab_id}.com",
        title=tab_id,
        role=BrowserTabRole(role_str),
        state=BrowserTabState.open,
        mission_id=mission_id,
        task_id=task_id,
    )


def _make_ctx(tab_summaries, dup_urls=None):
    wf = any(t["role"] == "WORKFLOW"   for t in tab_summaries)
    cp = any(t["role"] == "COMPARISON" for t in tab_summaries)
    rs = any(t["role"] == "RESEARCH"   for t in tab_summaries)
    return TabContext(
        mission_id="bm-m", tab_count=len(tab_summaries),
        active_tab_count=0, tab_summaries=tab_summaries,
        roles_present=list({t["role"] for t in tab_summaries}),
        primary_tab=None, active_tab=None,
        workflow_tab_present=wf, comparison_tab_present=cp, research_tab_present=rs,
        duplicate_urls=dup_urls or [], latency_ms=0,
    )


def _ts(tab_id, role="RESEARCH", state="OPEN", mission_id="m1"):
    return {
        "tab_id": tab_id, "url": f"https://{tab_id}.com", "title": tab_id,
        "role": role, "state": state, "mission_id": mission_id, "task_id": None,
        "updated_at": datetime.utcnow().isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 1. TabRegistry
# ─────────────────────────────────────────────────────────────────────────────

section("1. TabRegistry")

_i = 0
def _new_tab_id():
    global _i
    _i += 1
    return f"bm-{_i}"

_reset()
def bm_register():
    tab_reg.register(
        tab_id=str(uuid.uuid4())[:8],
        url="https://amazon.com", title="Amazon",
        role=BrowserTabRole.research,
        state=BrowserTabState.open,
        mission_id="bm-m1",
    )

bench("register (single new tab)", bm_register, target_ms=2.0)

# Pre-populate registry
_reset()
for i in range(10):
    _reg(f"existing-{i}", mission_id="bm-m1")

def bm_update():
    tab_reg.update("existing-0", role=BrowserTabRole.comparison)

bench("update (existing tab)",     bm_update,   target_ms=1.0)

def bm_close():
    _reg("close-target", mission_id="bm-m1")
    tab_reg.close("close-target")

bench("close (tab)",               bm_close,    target_ms=1.0)

def bm_get_hit():
    tab_reg.get("existing-0")

bench("get() - cache hit",         bm_get_hit,  target_ms=0.2)

def bm_get_miss():
    tab_reg.get("nonexistent-xyz")

bench("get() - cache miss",        bm_get_miss, target_ms=0.2)

def bm_all_open():
    tab_reg.all_open()

bench("all_open() (10 tabs)",      bm_all_open, target_ms=1.0)

def bm_for_mission():
    tab_reg.open_for_mission("bm-m1")

bench("open_for_mission() (10 tabs)", bm_for_mission, target_ms=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Mission + Task Tab Map
# ─────────────────────────────────────────────────────────────────────────────

section("2. Mission & Task Tab Map")
import app.tabs.mission_tab_map as mtm
import app.tabs.task_tab_map    as ttm

_reset()
for i in range(10):
    _reg(f"mm-{i}", mission_id="mm-m1", task_id="mm-t1")

def bm_mtm_list():
    mtm.list_open("mm-m1")

bench("mission_tab_map.list_open() (10 tabs)", bm_mtm_list, target_ms=1.0)

def bm_ttm_list():
    ttm.list_open("mm-t1")

bench("task_tab_map.list_open() (10 tabs)",    bm_ttm_list, target_ms=1.0)

def bm_mtm_primary():
    mtm.primary_tab("mm-m1")

bench("mission_tab_map.primary_tab()",         bm_mtm_primary, target_ms=0.5)

def bm_mtm_count():
    mtm.count("mm-m1")

bench("mission_tab_map.count()",               bm_mtm_count, target_ms=0.5)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Snapshot Manager
# ─────────────────────────────────────────────────────────────────────────────

section("3. TabSnapshotManager")
_reset()
snap_tab = create_tab("https://snap.com", "Snap", BrowserTabRole.research, tab_id="snap-bm")

def bm_snap_create():
    tab_snap.create(snap_tab, "tab_registered")

bench("snapshot.create()",          bm_snap_create, target_ms=1.0)

def bm_snap_load():
    tab_snap.load_latest("snap-bm")

bench("snapshot.load_latest()",     bm_snap_load, target_ms=0.5)

def bm_snap_load_all():
    tab_snap.load_all("snap-bm")

bench("snapshot.load_all()",        bm_snap_load_all, target_ms=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# 4. Restoration
# ─────────────────────────────────────────────────────────────────────────────

section("4. TabRestorationService")
from app.tabs.restoration import TabRestorationService

def bm_restoration_5():
    _reset()
    for i in range(5):
        t = create_tab(f"https://site-{i}.com", f"Site {i}",
                       BrowserTabRole.research, tab_id=f"rst-{i}")
        t.mission_id = "rst-m"
        tab_snap.create(t, "tab_registered")
    tab_reg._reset_for_testing()
    svc = TabRestorationService()
    svc.restore_all()

bench("restoration (5 tabs, cold)",  bm_restoration_5, reps=50, target_ms=20.0)


def bm_restoration_warmup():
    _reset()
    for i in range(5):
        t = create_tab(f"https://site-{i}.com", f"Site {i}",
                       BrowserTabRole.research, tab_id=f"wup-{i}")
        tab_snap.create(t, "tab_registered")
    from app.tabs.restoration import warmup
    tab_reg._reset_for_testing()
    warmup()

bench("warmup() (5 tabs)",           bm_restoration_warmup, reps=50, target_ms=20.0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. CrossTabContextBuilder
# ─────────────────────────────────────────────────────────────────────────────

section("5. CrossTabContextBuilder")
_reset()

def bm_ctx_empty():
    build_ctx("empty-mission")

bench("context.build() (0 tabs)",    bm_ctx_empty,  target_ms=1.0)

# 5 tabs
_reset()
for i in range(5):
    roles = ["RESEARCH", "RESEARCH", "COMPARISON", "WORKFLOW", "PRIMARY"]
    _reg(f"ctx5-{i}", roles[i], mission_id="ctx5-m")

def bm_ctx_5():
    build_ctx("ctx5-m")

bench("context.build() (5 tabs)",    bm_ctx_5, target_ms=5.0)

# 20 tabs
_reset()
for i in range(20):
    r = ["RESEARCH","COMPARISON","WORKFLOW","PRIMARY","REFERENCE"][i % 5]
    _reg(f"ctx20-{i}", r, mission_id="ctx20-m")

def bm_ctx_20():
    build_ctx("ctx20-m")

bench("context.build() (20 tabs)",   bm_ctx_20, target_ms=10.0)

# Duplicate detection
_reset()
for i in range(5):
    tab_reg.register(
        tab_id=f"dup-{i}", url="https://amazon.com", title=f"A{i}",
        role=BrowserTabRole.research, state=BrowserTabState.open,
        mission_id="dup-m",
    )

def bm_ctx_dup():
    build_ctx("dup-m")

bench("context.build() (dup URLs)",  bm_ctx_dup, target_ms=5.0)


# ─────────────────────────────────────────────────────────────────────────────
# 6. TabIntelligenceAnalyzer
# ─────────────────────────────────────────────────────────────────────────────

section("6. TabIntelligenceAnalyzer")

ctx_0  = _make_ctx([])
ctx_5  = _make_ctx([_ts(f"t{i}") for i in range(5)])
ctx_r2 = _make_ctx([_ts("t1","RESEARCH"), _ts("t2","RESEARCH")])

def bm_intel_empty():
    intel_analyze(ctx_0)

bench("intelligence.analyze() (0 tabs)",          bm_intel_empty, target_ms=1.0)

def bm_intel_5():
    intel_analyze(ctx_5)

bench("intelligence.analyze() (5 tabs)",          bm_intel_5,    target_ms=2.0)

def bm_intel_missing_comparison():
    intel_analyze(ctx_r2)

bench("intelligence.analyze() (MISSING_COMP rule)", bm_intel_missing_comparison, target_ms=2.0)

def bm_intel_high_readiness():
    intel_analyze(ctx_5, readiness_score=0.90)

bench("intelligence.analyze() (readiness=0.90)",  bm_intel_high_readiness, target_ms=2.0)


# ─────────────────────────────────────────────────────────────────────────────
# 7. Analytics
# ─────────────────────────────────────────────────────────────────────────────

section("7. TabAnalytics")

def bm_analytics_get():
    tab_an.get_analytics()

bench("analytics.get_analytics()",  bm_analytics_get, target_ms=0.1)

def bm_analytics_record():
    tab_an.record_tab_created()
    tab_an.record_snapshot()
    tab_an.record_mission_link()
    tab_an.record_context_build(latency_ms=5)
    tab_an.record_intelligence_run()

bench("analytics 5 records",        bm_analytics_record, target_ms=0.5)


# ─────────────────────────────────────────────────────────────────────────────
# 8. REST API Endpoints
# ─────────────────────────────────────────────────────────────────────────────

section("8. REST API")
from fastapi.testclient import TestClient
from app.main import app

_reset()
try:
    from app.mission import store as ms
    from app.unified import store as us
    ms._reset_for_testing()
    us._reset_for_testing()
except Exception:
    pass

client = TestClient(app)

# Pre-register a mission
resp_m = client.post("/mission/", json={"title": "Benchmark mission"})
mid = resp_m.json()["mission_id"]

# Pre-register tabs for read endpoints
for i in range(5):
    roles = ["RESEARCH", "COMPARISON", "WORKFLOW", "REFERENCE", "PRIMARY"]
    client.post("/tabs/register", json={
        "tab_id": f"bm-api-{i}", "url": f"https://site{i}.com",
        "title": f"Site {i}", "role": roles[i], "mission_id": mid,
    })


def bm_api_get_tabs():
    client.get("/tabs/")

bench("API GET /tabs/ (5 tabs)",        bm_api_get_tabs, reps=50, target_ms=10.0)


_i_post = [0]
def bm_api_register():
    _i_post[0] += 1
    client.post("/tabs/register", json={
        "tab_id": f"dyn-{_i_post[0]}", "url": "https://dynamic.com",
        "title": "Dynamic", "role": "REFERENCE",
    })

bench("API POST /tabs/register",        bm_api_register, reps=50, target_ms=10.0)


def bm_api_mission_tabs():
    client.get(f"/tabs/mission/{mid}")

bench("API GET /tabs/mission/{id}",     bm_api_mission_tabs, reps=50, target_ms=10.0)


def bm_api_get_tab():
    client.get("/tabs/bm-api-0")

bench("API GET /tabs/{tab_id}",         bm_api_get_tab, reps=50, target_ms=10.0)


def bm_api_inspect():
    client.get(f"/tabs/inspect/{mid}")

bench("API GET /tabs/inspect/{id}",     bm_api_inspect, reps=50, target_ms=25.0)


def bm_api_analytics():
    client.get("/tabs/analytics")

bench("API GET /tabs/analytics",        bm_api_analytics, reps=50, target_ms=10.0)


# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────

print("\n" + "="*70)
print("V6.0 Benchmark complete.")
print("All results above. Lines marked SLOW need optimization before ship.")
