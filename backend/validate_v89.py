"""
V8.9 Browser Runtime Layer — Validation Suite.

Minimum 500 checks across 22 sections.
Run: python validate_v89.py
"""
import sys
import time
import uuid
import pathlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
SECTION_RESULTS: list[tuple[str, int, int]] = []

def section(name: str):
    global PASS, FAIL
    SECTION_RESULTS.append((name, PASS, FAIL))
    print(f"\n[{name}]")

def check(label: str, cond: bool):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL: {label}")

def section_summary(name: str):
    prev = SECTION_RESULTS[-1]
    p = PASS - prev[1]
    f = FAIL - prev[2]
    print(f"  -> {p} pass, {f} fail")


def _reset_all():
    from app.runtime import registry, cache, events, analytics
    registry._reset_for_testing()
    cache._reset_for_testing()
    events._reset_for_testing()
    analytics._reset_for_testing()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Package structure
# ─────────────────────────────────────────────────────────────────────────────
section("1. Package Structure")
files = [
    "app/runtime/__init__.py",
    "app/runtime/models.py",
    "app/runtime/cache.py",
    "app/runtime/diff.py",
    "app/runtime/detector.py",
    "app/runtime/events.py",
    "app/runtime/registry.py",
    "app/runtime/analytics.py",
    "app/runtime/prefetch.py",
    "app/runtime/context.py",
    "app/runtime/sync_service.py",
    "app/runtime/inspector.py",
    "app/runtime/persistence.py",
    "app/schemas/runtime.py",
    "app/api/routes/runtime.py",
]
for f in files:
    check(f"file exists: {f}", pathlib.Path(f).exists())
section_summary("1. Package Structure")

# ─────────────────────────────────────────────────────────────────────────────
# 2. Models — enums
# ─────────────────────────────────────────────────────────────────────────────
section("2. Models — Enums")
from app.runtime.models import (
    RuntimeState, RuntimeEventType, PrefetchType, ALL_RUNTIME_EVENT_TYPES, CONTEXT_FIELDS,
)
check("RuntimeState has 4",        len(RuntimeState) == 4)
check("RuntimeState.idle",         RuntimeState.idle.value == "IDLE")
check("RuntimeState.active",       RuntimeState.active.value == "ACTIVE")
check("RuntimeState.syncing",      RuntimeState.syncing.value == "SYNCING")
check("RuntimeState.stale",        RuntimeState.stale.value == "STALE")
check("RuntimeState from string",  RuntimeState("ACTIVE") == RuntimeState.active)
check("RuntimeEventType has 7",    len(RuntimeEventType) == 7)
for et, val in [
    (RuntimeEventType.page_changed, "PAGE_CHANGED"),
    (RuntimeEventType.url_changed, "URL_CHANGED"),
    (RuntimeEventType.selection_changed, "SELECTION_CHANGED"),
    (RuntimeEventType.dom_updated, "DOM_UPDATED"),
    (RuntimeEventType.tab_switched, "TAB_SWITCHED"),
    (RuntimeEventType.mission_switched, "MISSION_SWITCHED"),
    (RuntimeEventType.task_switched, "TASK_SWITCHED"),
]:
    check(f"RuntimeEventType {val}", et.value == val)
check("ALL_RUNTIME_EVENT_TYPES = 7", len(ALL_RUNTIME_EVENT_TYPES) == 7)
check("PrefetchType has 4",        len(PrefetchType) == 4)
check("PrefetchType.none",         PrefetchType.none.value == "NONE")
check("PrefetchType.summarize",    PrefetchType.summarize.value == "SUMMARIZE")
check("PrefetchType.qa",           PrefetchType.qa.value == "QA")
check("PrefetchType.compare",      PrefetchType.compare.value == "COMPARE")
check("CONTEXT_FIELDS has 6",      len(CONTEXT_FIELDS) == 6)
for fname in ["last_read_view", "last_dom_summary", "last_selection",
              "last_url", "last_title", "last_scroll_position"]:
    check(f"CONTEXT_FIELDS has {fname}", fname in CONTEXT_FIELDS)
section_summary("2. Models — Enums")

# ─────────────────────────────────────────────────────────────────────────────
# 3. RuntimeSession model
# ─────────────────────────────────────────────────────────────────────────────
section("3. RuntimeSession Model")
from app.runtime.models import make_session, RuntimeSession
s = make_session(runtime_id="rt-v", browser_window_id="w1", active_tab_id="t1",
                 active_mission_id="m1", active_task_id="tk1", now=42.0)
check("runtime_id set",       s.runtime_id == "rt-v")
check("browser_window_id",    s.browser_window_id == "w1")
check("active_tab_id",        s.active_tab_id == "t1")
check("active_mission_id",    s.active_mission_id == "m1")
check("active_task_id",       s.active_task_id == "tk1")
check("state idle initial",   s.runtime_state == RuntimeState.idle)
check("created_at",           s.created_at == 42.0)
check("updated_at",           s.updated_at == 42.0)
auto = make_session(now=1.0)
check("auto id has rt- prefix", auto.runtime_id.startswith("rt-"))
check("auto ids unique",      make_session(now=1.0).runtime_id != make_session(now=1.0).runtime_id)
d = s.to_dict()
for k in ["runtime_id", "browser_window_id", "active_tab_id", "active_mission_id",
          "active_task_id", "runtime_state", "created_at", "updated_at"]:
    check(f"session.to_dict has {k}", k in d)
check("to_dict state is string", isinstance(d["runtime_state"], str))
section_summary("3. RuntimeSession Model")

# ─────────────────────────────────────────────────────────────────────────────
# 4. ContextSnapshot + ContextDiff
# ─────────────────────────────────────────────────────────────────────────────
section("4. ContextSnapshot + ContextDiff")
from app.runtime.models import ContextSnapshot, ContextDiff
snap = ContextSnapshot(last_url="u", last_title="t", last_read_view="r",
                       last_dom_summary="d", last_selection="s",
                       last_scroll_position=100, cached_at=1.0, dom_mutation_count=3)
check("field_value last_url",     snap.field_value("last_url") == "u")
check("field_value missing None", snap.field_value("nope") is None)
sd = snap.to_dict()
for k in list(CONTEXT_FIELDS) + ["cached_at", "dom_mutation_count"]:
    check(f"snapshot.to_dict has {k}", k in sd)
empty_diff = ContextDiff()
check("empty diff no changes",    not empty_diff.has_changes)
check("empty diff count 0",       empty_diff.changed_field_count == 0)
check("empty diff ratio 0",       empty_diff.diff_ratio == 0.0)
diff3 = ContextDiff(added={"a": 1}, removed={"b": 2}, modified={"c": 3})
check("diff count 3",             diff3.changed_field_count == 3)
check("diff has changes",         diff3.has_changes)
check("diff ratio 3/6",           diff3.diff_ratio == round(3 / 6, 4))
dd = diff3.to_dict()
for k in ["added", "removed", "modified", "changed_field_count", "has_changes", "diff_ratio"]:
    check(f"diff.to_dict has {k}", k in dd)
section_summary("4. ContextSnapshot + ContextDiff")

# ─────────────────────────────────────────────────────────────────────────────
# 5. RuntimeEvent + PrefetchHint + RuntimeContext models
# ─────────────────────────────────────────────────────────────────────────────
section("5. RuntimeEvent / PrefetchHint / RuntimeContext")
from app.runtime.models import (
    make_runtime_event, RuntimeEvent, PrefetchHint, RuntimeContext,
)
ev = make_runtime_event(RuntimeEventType.url_changed, "rt-1", now=5.0,
                        mission_id="m", task_id="tk", tab_id="tab", detail={"to": "u"})
check("event id has re- prefix",  ev.event_id.startswith("re-"))
check("event type",               ev.event_type == RuntimeEventType.url_changed)
check("event runtime_id",         ev.runtime_id == "rt-1")
check("event timestamp",          ev.timestamp == 5.0)
check("event mission_id",         ev.mission_id == "m")
check("event task_id",            ev.task_id == "tk")
check("event tab_id",             ev.tab_id == "tab")
check("event detail",             ev.detail == {"to": "u"})
ed = ev.to_dict()
for k in ["event_id", "event_type", "runtime_id", "timestamp", "mission_id", "task_id", "tab_id", "detail"]:
    check(f"event.to_dict has {k}", k in ed)
check("event to_dict type is str", ed["event_type"] == "URL_CHANGED")
h_none = PrefetchHint(prefetch_type=PrefetchType.none, reason="x")
h_sum  = PrefetchHint(prefetch_type=PrefetchType.summarize, reason="y", confidence=0.6)
check("none not actionable",      not h_none.is_actionable)
check("summarize actionable",     h_sum.is_actionable)
hd = h_sum.to_dict()
for k in ["prefetch_type", "reason", "confidence", "is_actionable", "signals"]:
    check(f"hint.to_dict has {k}", k in hd)
check("hint to_dict type is str", hd["prefetch_type"] == "SUMMARIZE")
rc = RuntimeContext(runtime_id="rt-1", active_mission_id="m", execution_ready=True)
check("context runtime_id",       rc.runtime_id == "rt-1")
check("context execution_ready",  rc.execution_ready is True)
rcd = rc.to_dict()
for k in ["runtime_id", "active_mission_id", "active_task_id", "mission_state",
          "approval_state", "authorization_state", "execution_ready", "evaluated_at"]:
    check(f"context.to_dict has {k}", k in rcd)
section_summary("5. RuntimeEvent / PrefetchHint / RuntimeContext")

# ─────────────────────────────────────────────────────────────────────────────
# 6. ContextCache — set/get/hit/miss
# ─────────────────────────────────────────────────────────────────────────────
section("6. ContextCache — Core")
from app.runtime import cache as ctx_cache
ctx_cache._reset_for_testing()
ctx_cache.set("rt-1", ContextSnapshot(last_url="http://a", cached_at=time.time()))
check("get returns snapshot",     ctx_cache.get("rt-1") is not None)
check("get correct url",          ctx_cache.get("rt-1").last_url == "http://a")
check("get missing None",         ctx_cache.get("absent") is None)
check("count = 1",                ctx_cache.count() == 1)
check("is_fresh True",            ctx_cache.is_fresh("rt-1"))
check("is_fresh absent False",    not ctx_cache.is_fresh("absent"))
check("age >= 0",                 ctx_cache.age_seconds("rt-1") >= 0.0)
check("age absent None",          ctx_cache.age_seconds("absent") is None)
# overwrite
ctx_cache.set("rt-1", ContextSnapshot(last_url="http://b", cached_at=time.time()))
check("overwrite works",          ctx_cache.get("rt-1").last_url == "http://b")
# peek does not count hit
ctx_cache._reset_for_testing()
ctx_cache.set("rt-1", ContextSnapshot(cached_at=time.time()))
ctx_cache.peek("rt-1")
check("peek no hit count",        ctx_cache.stats()["cache_hits"] == 0)
ctx_cache.get("rt-1")  # hit
ctx_cache.get("absent")  # miss
st = ctx_cache.stats()
check("hits 1",                   st["cache_hits"] == 1)
check("misses 1",                 st["cache_misses"] == 1)
check("hit_ratio 0.5",            st["hit_ratio"] == 0.5)
check("ttl 300",                  st["ttl_seconds"] == 300.0)
for k in ["cached_runtimes", "cache_hits", "cache_misses", "hit_ratio", "ttl_seconds"]:
    check(f"cache.stats has {k}",  k in st)
check("invalidate True",          ctx_cache.invalidate("rt-1") is True)
check("invalidate absent False",  ctx_cache.invalidate("rt-1") is False)
section_summary("6. ContextCache — Core")

# ─────────────────────────────────────────────────────────────────────────────
# 7. ContextCache — TTL
# ─────────────────────────────────────────────────────────────────────────────
section("7. ContextCache — TTL")
from app.runtime.cache import ContextCache
c = ContextCache(ttl=0.05)
c.set("rt-x", ContextSnapshot(cached_at=time.time()))
check("fresh before ttl",         c.is_fresh("rt-x"))
time.sleep(0.08)
check("get None after ttl",       c.get("rt-x") is None)
check("not fresh after ttl",      not c.is_fresh("rt-x"))
check("ttl miss counted",         c.stats()["cache_misses"] >= 1)
section_summary("7. ContextCache — TTL")

# ─────────────────────────────────────────────────────────────────────────────
# 8. ContextDiffEngine
# ─────────────────────────────────────────────────────────────────────────────
section("8. ContextDiffEngine")
from app.runtime import diff as diff_engine
# No prior → all added
d_first = diff_engine.compute(None, ContextSnapshot(last_url="u", last_title="t"))
check("no prior url added",       "last_url" in d_first.added)
check("no prior title added",     "last_title" in d_first.added)
check("none field not added",     "last_selection" not in d_first.added)
# Added
d_add = diff_engine.compute(ContextSnapshot(last_url="u"),
                            ContextSnapshot(last_url="u", last_title="t"))
check("added title only",         d_add.added == {"last_title": "t"})
# Removed
d_rem = diff_engine.compute(ContextSnapshot(last_url="u", last_title="t"),
                            ContextSnapshot(last_url="u"))
check("removed title",            d_rem.removed == {"last_title": "t"})
check("removed carries old",      d_rem.removed["last_title"] == "t")
# Modified
d_mod = diff_engine.compute(ContextSnapshot(last_url="a"),
                            ContextSnapshot(last_url="b"))
check("modified url",             d_mod.modified == {"last_url": "b"})
# Unchanged
d_same = diff_engine.compute(ContextSnapshot(last_url="a", last_title="t"),
                             ContextSnapshot(last_url="a", last_title="t"))
check("unchanged no changes",     not d_same.has_changes)
# Mixed
d_mix = diff_engine.compute(ContextSnapshot(last_url="a", last_title="t"),
                            ContextSnapshot(last_url="b", last_selection="s"))
check("mixed modified url",        d_mix.modified == {"last_url": "b"})
check("mixed added selection",     d_mix.added == {"last_selection": "s"})
check("mixed removed title",       d_mix.removed == {"last_title": "t"})
check("mixed count 3",             d_mix.changed_field_count == 3)
# Ratio
d_full = diff_engine.compute(None, ContextSnapshot(
    last_read_view="r", last_dom_summary="d", last_selection="s",
    last_url="u", last_title="t", last_scroll_position=1))
check("full diff ratio 1.0",       d_full.diff_ratio == 1.0)
check("one field ratio",           d_mod.diff_ratio == round(1 / 6, 4))
# scroll position 0 vs 0 unchanged
d_scroll = diff_engine.compute(ContextSnapshot(last_scroll_position=0),
                               ContextSnapshot(last_scroll_position=0))
check("scroll 0 unchanged",        not d_scroll.has_changes)
d_scroll2 = diff_engine.compute(ContextSnapshot(last_scroll_position=0),
                                ContextSnapshot(last_scroll_position=500))
check("scroll modified",           d_scroll2.modified["last_scroll_position"] == 500)
section_summary("8. ContextDiffEngine")

# ─────────────────────────────────────────────────────────────────────────────
# 9. DOMChangeDetector
# ─────────────────────────────────────────────────────────────────────────────
section("9. DOMChangeDetector")
from app.runtime import detector
def _types(evs): return [e.event_type for e in evs]
e_title = detector.detect("rt-1", ContextSnapshot(last_title="A"),
                          ContextSnapshot(last_title="B"), now=1.0)
check("title change PAGE_CHANGED",  RuntimeEventType.page_changed in _types(e_title))
e_url = detector.detect("rt-1", ContextSnapshot(last_url="a"),
                        ContextSnapshot(last_url="b"), now=1.0)
check("url change URL_CHANGED",     RuntimeEventType.url_changed in _types(e_url))
e_sel = detector.detect("rt-1", ContextSnapshot(last_selection="x"),
                        ContextSnapshot(last_selection="y"), now=1.0)
check("selection SELECTION_CHANGED", RuntimeEventType.selection_changed in _types(e_sel))
e_dom = detector.detect("rt-1", None, ContextSnapshot(dom_mutation_count=5), now=1.0)
check("dom mutation DOM_UPDATED",   RuntimeEventType.dom_updated in _types(e_dom))
e_nodom = detector.detect("rt-1", None, ContextSnapshot(dom_mutation_count=0, last_url="a"), now=1.0)
check("zero mutation no DOM event", RuntimeEventType.dom_updated not in _types(e_nodom))
e_sametitle = detector.detect("rt-1", ContextSnapshot(last_title="A"),
                              ContextSnapshot(last_title="A"), now=1.0)
check("same title no event",        RuntimeEventType.page_changed not in _types(e_sametitle))
e_empty = detector.detect("rt-1", None, ContextSnapshot(), now=1.0)
check("empty snapshot no events",   e_empty == [])
e_tab = detector.detect("rt-1", None, ContextSnapshot(), now=1.0, tab_id="t2", old_tab_id="t1")
check("tab switch TAB_SWITCHED",    RuntimeEventType.tab_switched in _types(e_tab))
e_tabsame = detector.detect("rt-1", None, ContextSnapshot(), now=1.0, tab_id="t1", old_tab_id="t1")
check("same tab no event",          RuntimeEventType.tab_switched not in _types(e_tabsame))
e_mis = detector.detect("rt-1", None, ContextSnapshot(), now=1.0, mission_id="m2", old_mission_id="m1")
check("mission switch event",       RuntimeEventType.mission_switched in _types(e_mis))
e_task = detector.detect("rt-1", None, ContextSnapshot(), now=1.0, task_id="tk2", old_task_id="tk1")
check("task switch event",          RuntimeEventType.task_switched in _types(e_task))
e_taboldnone = detector.detect("rt-1", None, ContextSnapshot(), now=1.0, tab_id="t1", old_tab_id=None)
check("first tab no switch event",  RuntimeEventType.tab_switched not in _types(e_taboldnone))
# detail + fields
url_ev = [e for e in detector.detect("rt-X", ContextSnapshot(last_url="a"),
          ContextSnapshot(last_url="b"), now=9.0) if e.event_type == RuntimeEventType.url_changed][0]
check("url detail from",            url_ev.detail["from"] == "a")
check("url detail to",              url_ev.detail["to"] == "b")
check("event runtime_id propagated", url_ev.runtime_id == "rt-X")
check("event timestamp propagated", url_ev.timestamp == 9.0)
# multiple
e_multi = detector.detect("rt-1", ContextSnapshot(last_url="a", last_title="A"),
                          ContextSnapshot(last_url="b", last_title="B", dom_mutation_count=3), now=1.0)
check("multi 3 events",             len(e_multi) == 3)
section_summary("9. DOMChangeDetector")

# ─────────────────────────────────────────────────────────────────────────────
# 10. RuntimeEventQueue
# ─────────────────────────────────────────────────────────────────────────────
section("10. RuntimeEventQueue")
from app.runtime import events as eq
from app.runtime.events import RuntimeEventQueue, QUEUE_LIMIT, MAX_PER_RUNTIME
eq._reset_for_testing()
eq.enqueue(make_runtime_event(RuntimeEventType.page_changed, "rt-1", now=1.0))
check("count 1",                    eq.count() == 1)
n = eq.enqueue_many([make_runtime_event(RuntimeEventType.url_changed, "rt-1", now=2.0),
                     make_runtime_event(RuntimeEventType.dom_updated, "rt-1", now=3.0)])
check("enqueue_many returns 2",     n == 2)
check("count 3",                    eq.count() == 3)
check("total_enqueued 3",           eq.stats()["total_enqueued"] == 3)
check("get_for_runtime 3",          len(eq.get_for_runtime("rt-1")) == 3)
check("newest first",               eq.get_for_runtime("rt-1")[0].event_type == RuntimeEventType.dom_updated)
check("count_for_runtime 3",        eq.count_for_runtime("rt-1") == 3)
check("recent_global 3",            len(eq.recent_global()) == 3)
check("limit respected",            len(eq.get_for_runtime("rt-1", limit=2)) == 2)
check("absent empty",               eq.get_for_runtime("absent") == [])
summ = eq.summary("rt-1")
check("summary event_count 3",      summ["event_count"] == 3)
check("summary type_counts dict",   isinstance(summ["type_counts"], dict))
check("summary latest not None",    summ["latest_event"] is not None)
check("rt-1 in runtimes",           "rt-1" in eq.runtimes_with_events())
for k in ["queued_global", "total_enqueued", "runtime_keys", "queue_limit"]:
    check(f"queue.stats has {k}",   k in eq.stats())
check("default queue limit 500",    eq.stats()["queue_limit"] == QUEUE_LIMIT)
check("QUEUE_LIMIT is 500",         QUEUE_LIMIT == 500)
# global cap
qcap = RuntimeEventQueue(limit=5)
for i in range(10):
    qcap.enqueue(make_runtime_event(RuntimeEventType.page_changed, "rt-1", now=float(i)))
check("global cap enforced",        qcap.count() == 5)
# per-runtime cap
eq._reset_for_testing()
for i in range(250):
    eq.enqueue(make_runtime_event(RuntimeEventType.page_changed, "rt-1", now=float(i)))
check("per-runtime cap <= 200",     eq.count_for_runtime("rt-1") <= MAX_PER_RUNTIME)
eq._reset_for_testing()
check("reset clears",               eq.count() == 0)
section_summary("10. RuntimeEventQueue")

# ─────────────────────────────────────────────────────────────────────────────
# 11. RuntimeSessionRegistry — CRUD
# ─────────────────────────────────────────────────────────────────────────────
section("11. RuntimeSessionRegistry — CRUD")
from app.runtime import registry as sreg
sreg._reset_for_testing()
now_w = time.time()
sreg.add(make_session(runtime_id="rt-1", active_mission_id="m-A", active_tab_id="tab-1", now=now_w))
sreg.add(make_session(runtime_id="rt-2", active_mission_id="m-A", active_tab_id="tab-2", now=now_w))
sreg.add(make_session(runtime_id="rt-3", active_mission_id="m-B", active_tab_id="tab-3", now=now_w))
check("get rt-1",                   sreg.get("rt-1") is not None)
check("get absent None",            sreg.get("absent") is None)
check("count 3",                    sreg.count() == 3)
check("list_all 3",                 len(sreg.list_all()) == 3)
check("list_all limit",             len(sreg.list_all(limit=2)) == 2)
check("list_for_mission m-A 2",     len(sreg.list_for_mission("m-A")) == 2)
check("list_for_mission m-B 1",     len(sreg.list_for_mission("m-B")) == 1)
check("list_for_mission absent",    sreg.list_for_mission("absent") == [])
sm = sreg.summary_for_mission("m-A")
check("summary total 2",            sm["total_sessions"] == 2)
for k in ["total_sessions", "active_sessions", "active_tab_id", "latest_update", "runtime_ids"]:
    check(f"summary has {k}",       k in sm)
check("empty summary 0",            sreg.summary_for_mission("absent")["total_sessions"] == 0)
section_summary("11. RuntimeSessionRegistry — CRUD")

# ─────────────────────────────────────────────────────────────────────────────
# 12. RuntimeSessionRegistry — update / state / TTL
# ─────────────────────────────────────────────────────────────────────────────
section("12. RuntimeSessionRegistry — Update / State / TTL")
sreg._reset_for_testing()
sreg.add(make_session(runtime_id="rt-1", active_mission_id="m-A", now=time.time()))
check("touch True",                 sreg.touch("rt-1", wall_now=time.time() + 5) is True)
check("touch absent False",         sreg.touch("absent", wall_now=time.time()) is False)
sreg.update_session("rt-1", wall_now=time.time(), active_tab_id="tab-99")
check("update tab",                 sreg.get("rt-1").active_tab_id == "tab-99")
sreg.update_session("rt-1", wall_now=time.time(), runtime_state=RuntimeState.active)
check("update state active",        sreg.get("rt-1").runtime_state == RuntimeState.active)
check("update absent None",         sreg.update_session("absent", wall_now=time.time()) is None)
sreg.update_session("rt-1", wall_now=time.time(), active_mission_id="m-B")
check("reindex old mission empty",  len(sreg.list_for_mission("m-A")) == 0)
check("reindex new mission 1",      len(sreg.list_for_mission("m-B")) == 1)
check("set_state True",             sreg.set_state("rt-1", RuntimeState.stale) is True)
check("state stale",                sreg.get("rt-1").runtime_state == RuntimeState.stale)
check("set_state absent False",     sreg.set_state("absent", RuntimeState.stale) is False)
check("count_by_state stale 1",     sreg.count_by_state(RuntimeState.stale) == 1)
for k in ["cached_sessions", "total_added", "total_evicted", "mission_keys", "ttl_seconds"]:
    check(f"reg.stats has {k}",     k in sreg.stats())
from app.runtime.registry import RuntimeSessionRegistry
rttl = RuntimeSessionRegistry(ttl=0.05)
rttl.add(make_session(runtime_id="rt-x", now=time.time()))
time.sleep(0.08)
check("session expires",            rttl.get("rt-x") is None)
check("expired count 0",            rttl.count() == 0)
sreg._reset_for_testing()
check("reset clears",               sreg.count() == 0)
section_summary("12. RuntimeSessionRegistry — Update / State / TTL")

# ─────────────────────────────────────────────────────────────────────────────
# 13. RuntimeAnalytics
# ─────────────────────────────────────────────────────────────────────────────
section("13. RuntimeAnalytics")
from app.runtime import analytics as anal
anal._reset_for_testing()
a0 = anal.get_analytics()
for k in ["runtime_uptime_seconds", "syncs", "cached_requests", "cache_hits",
          "cache_misses", "cache_hit_ratio", "avg_context_diff_ratio",
          "prefetch_opportunities", "total_events", "event_rate"]:
    check(f"analytics has {k}",     k in a0)
check("initial syncs 0",            a0["syncs"] == 0)
check("initial uptime 0",           a0["runtime_uptime_seconds"] == 0.0)
anal.record_sync(wall_now=100.0, cache_hit=False, diff_ratio=0.2, event_count=2, prefetch=False)
anal.record_sync(wall_now=110.0, cache_hit=True,  diff_ratio=0.4, event_count=3, prefetch=True)
a1 = anal.get_analytics(wall_now=110.0)
check("syncs 2",                    a1["syncs"] == 2)
check("cache_hits 1",               a1["cache_hits"] == 1)
check("cache_misses 1",             a1["cache_misses"] == 1)
check("cached_requests 1",          a1["cached_requests"] == 1)
check("hit_ratio 0.5",              a1["cache_hit_ratio"] == 0.5)
check("avg_diff 0.3",               a1["avg_context_diff_ratio"] == round(0.3, 4))
check("total_events 5",             a1["total_events"] == 5)
check("event_rate 2.5",             a1["event_rate"] == round(5 / 2, 4))
check("prefetch_opportunities 1",   a1["prefetch_opportunities"] == 1)
check("uptime 10",                  a1["runtime_uptime_seconds"] == 10.0)
check("uptime never negative",      anal.get_analytics(wall_now=50.0)["runtime_uptime_seconds"] >= 0.0)
anal._reset_for_testing()
check("reset syncs 0",              anal.get_analytics()["syncs"] == 0)
check("reset uptime 0",             anal.get_analytics()["runtime_uptime_seconds"] == 0.0)
section_summary("13. RuntimeAnalytics")

# ─────────────────────────────────────────────────────────────────────────────
# 14. PredictivePrefetch
# ─────────────────────────────────────────────────────────────────────────────
section("14. PredictivePrefetch")
from app.runtime import prefetch
def _pf_ev(et): return make_runtime_event(et, "rt-1", now=1.0)
# COMPARE via 2 url changes
h = prefetch.predict(None, [_pf_ev(RuntimeEventType.url_changed)] * 2,
                     ContextSnapshot(last_title="x"))
check("2 url COMPARE",              h.prefetch_type == PrefetchType.compare)
# COMPARE via 2 tab switches
h = prefetch.predict(None, [_pf_ev(RuntimeEventType.tab_switched)] * 2,
                     ContextSnapshot())
check("2 tab COMPARE",              h.prefetch_type == PrefetchType.compare)
# COMPARE via title keyword
h = prefetch.predict(None, [], ContextSnapshot(last_title="iPhone vs Android"))
check("title vs COMPARE",           h.prefetch_type == PrefetchType.compare)
h = prefetch.predict(None, [], ContextSnapshot(last_title="Best Laptop Review"))
check("title review COMPARE",       h.prefetch_type == PrefetchType.compare)
check("compare actionable",         h.is_actionable)
# QA via 3 selections
h = prefetch.predict(None, [_pf_ev(RuntimeEventType.selection_changed)] * 3,
                     ContextSnapshot(last_title="x"))
check("3 selections QA",            h.prefetch_type == PrefetchType.qa)
h = prefetch.predict(None, [_pf_ev(RuntimeEventType.selection_changed)] * 2,
                     ContextSnapshot(last_title="x"))
check("2 selections not QA",        h.prefetch_type != PrefetchType.qa)
# SUMMARIZE long article, no nav
h = prefetch.predict(None, [], ContextSnapshot(last_read_view="x" * 3000, last_title="Article"))
check("long article SUMMARIZE",     h.prefetch_type == PrefetchType.summarize)
h = prefetch.predict(None, [], ContextSnapshot(last_read_view="short", last_title="x"))
check("short not summarize",        h.prefetch_type != PrefetchType.summarize)
# NONE
h = prefetch.predict(None, [], ContextSnapshot(last_read_view="short", last_title="x"))
check("no signal NONE",             h.prefetch_type == PrefetchType.none)
check("none not actionable",        not h.is_actionable)
check("none zero confidence",       h.confidence == 0.0)
# signals + dict
h = prefetch.predict(None, [_pf_ev(RuntimeEventType.selection_changed)] * 3, ContextSnapshot())
check("signals selection 3",        h.signals["selection_changes"] == 3)
for k in ["prefetch_type", "reason", "confidence", "is_actionable", "signals"]:
    check(f"hint.to_dict has {k}",  k in h.to_dict())
# priority: compare over qa
h = prefetch.predict(None, [_pf_ev(RuntimeEventType.url_changed)] * 2 +
                     [_pf_ev(RuntimeEventType.selection_changed)] * 3, ContextSnapshot())
check("compare beats qa",           h.prefetch_type == PrefetchType.compare)
# long article with nav → compare
h = prefetch.predict(None, [_pf_ev(RuntimeEventType.url_changed)] * 2,
                     ContextSnapshot(last_read_view="x" * 3000))
check("long+nav COMPARE",           h.prefetch_type == PrefetchType.compare)
section_summary("14. PredictivePrefetch")

# ─────────────────────────────────────────────────────────────────────────────
# 15. RuntimeSyncService
# ─────────────────────────────────────────────────────────────────────────────
section("15. RuntimeSyncService")
from app.runtime import sync_service
_reset_all()
r1 = sync_service.sync(active_mission_id="m-1", active_tab_id="tab-1",
                       last_url="http://a", last_title="A")
check("sync created True",          r1.created is True)
check("sync runtime_id prefix",     r1.runtime_id.startswith("rt-"))
check("first cache miss",           r1.cache_hit is False)
check("first diff has changes",     r1.diff["has_changes"] is True)
check("session in registry",        sreg.get(r1.runtime_id) is not None)
check("session state ACTIVE",       sreg.get(r1.runtime_id).runtime_state == RuntimeState.active)
check("url event emitted",          "URL_CHANGED" in [e["event_type"] for e in r1.events])
check("events enqueued",            eq.count_for_runtime(r1.runtime_id) >= 1)
check("snapshot cached",            ctx_cache.peek(r1.runtime_id) is not None)
check("context mission",            r1.context["active_mission_id"] == "m-1")
check("prefetch present",           "prefetch_type" in r1.prefetch)
check("latency >= 0",               r1.latency_ms >= 0.0)
check("session in result",          r1.session is not None)
r2 = sync_service.sync(runtime_id=r1.runtime_id, active_mission_id="m-1",
                       active_tab_id="tab-1", last_url="http://b", last_title="A")
check("reuse created False",        r2.created is False)
check("second cache hit",           r2.cache_hit is True)
check("url modified in diff",       "last_url" in r2.diff["modified"])
check("url change event",           "URL_CHANGED" in [e["event_type"] for e in r2.events])
r3 = sync_service.sync(runtime_id=r1.runtime_id, active_tab_id="tab-2",
                       last_url="http://b", last_title="A")
check("tab switch event",           "TAB_SWITCHED" in [e["event_type"] for e in r3.events])
r4 = sync_service.sync(runtime_id=r1.runtime_id, active_tab_id="tab-2",
                       last_url="http://b", last_title="A")
check("no change no events",        len(r4.events) == 0)
check("analytics syncs 4",          anal.get_analytics()["syncs"] == 4)
rd = r1.to_dict()
for k in ["runtime_id", "created", "cache_hit", "diff", "events", "prefetch",
          "context", "session", "latency_ms"]:
    check(f"sync result has {k}",   k in rd)
section_summary("15. RuntimeSyncService")

# ─────────────────────────────────────────────────────────────────────────────
# 16. RuntimeContext builder
# ─────────────────────────────────────────────────────────────────────────────
section("16. RuntimeContext Builder")
from app.runtime import context as rt_context
_reset_all()
rsync = sync_service.sync(active_mission_id="m-ctx", active_task_id="t-ctx", last_url="http://a")
ctx = rt_context.build(rsync.runtime_id)
check("context runtime_id",         ctx.runtime_id == rsync.runtime_id)
check("context mission",            ctx.active_mission_id == "m-ctx")
check("context task",               ctx.active_task_id == "t-ctx")
check("execution_ready default F",  ctx.execution_ready is False)
check("evaluated_at set",           ctx.evaluated_at > 0)
# unknown runtime: still builds
ctx_unknown = rt_context.build("rt-unknown")
check("unknown runtime builds",     ctx_unknown.runtime_id == "rt-unknown")
check("unknown no mission",         ctx_unknown.active_mission_id is None)
section_summary("16. RuntimeContext Builder")

# ─────────────────────────────────────────────────────────────────────────────
# 17. RuntimeInspector
# ─────────────────────────────────────────────────────────────────────────────
section("17. RuntimeInspector")
from app.runtime import inspector as insp
_reset_all()
rid = sync_service.sync(active_mission_id="m-insp", active_tab_id="tab-1",
                        last_url="http://a", last_title="A",
                        last_read_view="x" * 100).runtime_id
result = insp.inspect(rid)
for k in ["runtime_id", "session", "cache_health", "context_freshness",
          "event_summary", "recent_events", "prefetch", "runtime_context",
          "authorization_runtime", "browser_sync", "analytics",
          "registry_stats", "cache_stats", "queue_stats", "latency_ms"]:
    check(f"inspect has {k}",       k in result)
check("inspect runtime_id",         result["runtime_id"] == rid)
check("inspect session not None",   result["session"] is not None)
check("cache has_context True",     result["cache_health"]["has_context"] is True)
check("cache is_fresh True",        result["cache_health"]["is_fresh"] is True)
check("context_summary url",        result["cache_health"]["context_summary"]["last_url"] == "http://a")
check("freshness label present",    "label" in result["context_freshness"])
check("auth_runtime exec_ready",    "execution_ready" in result["authorization_runtime"])
check("exec_ready False no auth",   result["authorization_runtime"]["execution_ready"] is False)
check("latency >= 0",               result["latency_ms"] >= 0.0)
# missing runtime
r_absent = insp.inspect("rt-absent")
check("absent no session",          r_absent["session"] is None)
check("absent no context",          r_absent["cache_health"]["has_context"] is False)
section_summary("17. RuntimeInspector")

# ─────────────────────────────────────────────────────────────────────────────
# 18. Persistence stub
# ─────────────────────────────────────────────────────────────────────────────
section("18. Persistence Stub")
from app.runtime.persistence import RuntimePersistence, RUNTIME_PERSISTENCE
p = RuntimePersistence()
check("flag False",                 RUNTIME_PERSISTENCE is False)
check("enabled False",              p.enabled() is False)
check("save no-op",                 p.save(make_session(now=1.0)) is None)
check("load empty",                 p.load_for_mission("m-1") == [])
check("delete 0",                   p.delete_for_runtime("rt-1") == 0)
section_summary("18. Persistence Stub")

# ─────────────────────────────────────────────────────────────────────────────
# 19. Schemas
# ─────────────────────────────────────────────────────────────────────────────
section("19. Schemas (Pydantic)")
from app.schemas.runtime import (
    RuntimeSessionSchema, ContextSnapshotSchema, ContextDiffSchema,
    RuntimeEventSchema, PrefetchHintSchema, RuntimeContextSchema,
    RuntimeAnalyticsSchema, RuntimeInspectorSchema, RuntimeSyncRequest,
    RuntimeSyncResponse,
)
check("RuntimeSessionSchema",       RuntimeSessionSchema(runtime_id="rt-1").runtime_id == "rt-1")
check("session default state",      RuntimeSessionSchema(runtime_id="rt-1").runtime_state == "IDLE")
check("ContextSnapshotSchema",      ContextSnapshotSchema().dom_mutation_count == 0)
check("ContextDiffSchema",          ContextDiffSchema().has_changes is False)
check("RuntimeEventSchema",         RuntimeEventSchema(event_id="e", event_type="URL_CHANGED",
                                       runtime_id="rt-1").event_type == "URL_CHANGED")
check("PrefetchHintSchema default", PrefetchHintSchema().prefetch_type == "NONE")
check("RuntimeContextSchema",       RuntimeContextSchema(runtime_id="rt-1").execution_ready is False)
check("RuntimeAnalyticsSchema",     RuntimeAnalyticsSchema().syncs == 0)
check("RuntimeInspectorSchema",     RuntimeInspectorSchema(runtime_id="rt-1").runtime_id == "rt-1")
check("RuntimeSyncRequest default", RuntimeSyncRequest().dom_mutation_count == 0)
check("sync request optional id",   RuntimeSyncRequest().runtime_id is None)
resp = RuntimeSyncResponse(runtime_id="rt-1", diff=ContextDiffSchema())
check("RuntimeSyncResponse",        resp.runtime_id == "rt-1")
check("sync response created F",    resp.created is False)
section_summary("19. Schemas (Pydantic)")

# ─────────────────────────────────────────────────────────────────────────────
# 20. REST API — registration + responses
# ─────────────────────────────────────────────────────────────────────────────
section("20. REST API")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
routes = {r.path for r in app.routes}
check("route /runtime",             "/runtime" in routes)
check("route /runtime/context",     "/runtime/context" in routes)
check("route /runtime/events",      "/runtime/events" in routes)
check("route /runtime/cache",       "/runtime/cache" in routes)
check("route /runtime/analytics",   "/runtime/analytics" in routes)
check("route /runtime/inspect",     "/runtime/inspect" in routes)
check("route /runtime/sync",        "/runtime/sync" in routes)
_reset_all()
r = client.get("/runtime")
check("GET /runtime 200",           r.status_code == 200)
check("GET /runtime empty list",    r.json() == [])
sresp = client.post("/runtime/sync", json={"last_url": "http://a", "last_title": "A",
                                            "active_mission_id": "m-api"})
check("POST /runtime/sync 200",     sresp.status_code == 200)
rid_api = sresp.json()["runtime_id"]
check("sync returns runtime_id",    rid_api.startswith("rt-"))
check("sync created True",          sresp.json()["created"] is True)
check("GET /runtime now 1",         len(client.get("/runtime").json()) == 1)
check("filter mission",             len(client.get("/runtime?mission_id=m-api").json()) == 1)
check("filter state ACTIVE",        len(client.get("/runtime?state=ACTIVE").json()) == 1)
check("invalid state 400",          client.get("/runtime?state=BOGUS").status_code == 400)
check("context 200",                client.get(f"/runtime/context?runtime_id={rid_api}").status_code == 200)
check("context mission",            client.get(f"/runtime/context?runtime_id={rid_api}").json()["active_mission_id"] == "m-api")
check("context absent 404",         client.get("/runtime/context?runtime_id=rt-absent").status_code == 404)
check("events 200",                 client.get(f"/runtime/events?runtime_id={rid_api}").status_code == 200)
check("events nonempty",            len(client.get(f"/runtime/events?runtime_id={rid_api}").json()) >= 1)
check("events global",              client.get("/runtime/events").status_code == 200)
check("cache 200",                  client.get(f"/runtime/cache?runtime_id={rid_api}").status_code == 200)
check("cache snapshot url",         client.get(f"/runtime/cache?runtime_id={rid_api}").json()["snapshot"]["last_url"] == "http://a")
check("cache absent 404",           client.get("/runtime/cache?runtime_id=rt-absent").status_code == 404)
check("analytics 200",              client.get("/runtime/analytics").status_code == 200)
check("analytics syncs >=1",        client.get("/runtime/analytics").json()["syncs"] >= 1)
check("inspect 200",                client.get(f"/runtime/inspect?runtime_id={rid_api}").status_code == 200)
check("inspect absent 404",         client.get("/runtime/inspect?runtime_id=rt-absent").status_code == 404)
section_summary("20. REST API")

# ─────────────────────────────────────────────────────────────────────────────
# 21. Cross-layer integration (mission / browser / authorization)
# ─────────────────────────────────────────────────────────────────────────────
section("21. Cross-Layer Integration")
_reset_all()
# Mission inspector includes runtime section
from app.mission import store as ms
from app.mission.models import Mission, MissionState
ms.put(Mission("m-rt-val", "RT Val", "test", MissionState.active))
client.post("/runtime/sync", json={"active_mission_id": "m-rt-val", "active_tab_id": "tab-7",
                                    "last_url": "http://a"})
mi = client.get("/mission/m-rt-val/inspect")
check("mission inspect 200",        mi.status_code == 200)
check("mission inspect has runtime", "runtime" in mi.json())
rt_section = mi.json()["runtime"]
check("runtime section not None",   rt_section is not None)
check("runtime active_tab",         rt_section["active_tab_id"] == "tab-7")
check("runtime_health present",     "runtime_health" in rt_section)
check("cache_health present",       "cache_health" in rt_section)
check("event_count present",        "event_count" in rt_section)
check("context_freshness present",  "context_freshness" in rt_section)
# Browser sync linkage (V7.0 not duplicated)
from app.browser import registry as browser_reg
from app.browser.models import make_event, BrowserEventType
browser_reg._reset_for_testing()
browser_reg.register(make_event(BrowserEventType.page_loaded, "tab-1",
                                url="http://a", mission_id="m-bs-val"))
rid_bs = client.post("/runtime/sync", json={"active_mission_id": "m-bs-val",
                     "active_tab_id": "tab-1", "last_url": "http://a"}).json()["runtime_id"]
insp_bs = client.get(f"/runtime/inspect?runtime_id={rid_bs}").json()
check("browser_sync linked",        insp_bs["browser_sync"] is not None)
check("browser_sync mission",       insp_bs["browser_sync"]["linked_mission"] == "m-bs-val")
check("runtime not duplicating browser events", browser_reg.count() == 1)  # only the one we added
browser_reg._reset_for_testing()
# Authorization runtime (read-only)
from app.governance import registry as gov_reg
from app.governance.models import make_contract
from app.authorization import registry as auth_reg
gov_reg._reset_for_testing(); auth_reg._reset_for_testing()
c = make_contract(str(uuid.uuid4()), True, "tester", time.time(),
                  "TRUST_ENGINE", str(uuid.uuid4()), "HIGH",
                  mission_id="m-auth-val", task_id="t-1", ttl_seconds=3600)
gov_reg.add(c)
client.post(f"/authorization/evaluate/{c.contract_id}")
rid_auth = client.post("/runtime/sync", json={"active_mission_id": "m-auth-val",
                       "last_url": "http://a"}).json()["runtime_id"]
ctx_auth = client.get(f"/runtime/context?runtime_id={rid_auth}").json()
check("execution_ready True with auth", ctx_auth["execution_ready"] is True)
check("authorization_state present",    ctx_auth["authorization_state"] is not None)
check("active_authorizations >= 1",     ctx_auth["authorization_state"]["active_authorizations"] >= 1)
# Runtime must NOT mutate authorization
auth_count_before = auth_reg.count()
client.post("/runtime/sync", json={"active_mission_id": "m-auth-val", "last_url": "http://b"})
check("runtime does not change auth",   auth_reg.count() == auth_count_before)
gov_reg._reset_for_testing(); auth_reg._reset_for_testing()
section_summary("21. Cross-Layer Integration")

# ─────────────────────────────────────────────────────────────────────────────
# 22. Safety — no forbidden patterns
# ─────────────────────────────────────────────────────────────────────────────
section("22. Safety — No Forbidden Patterns")
forbidden = [
    "subprocess", "os.system", "import webbrowser",
    "playwright", "selenium",
    "workflow_dispatch", "dispatch_workflow", "agent_swarm",
    "execute_task(", "run_browser(", "automate(",
    "anthropic", "openai", "llm_client", "call_llm", ".generate(", "requests.get", "requests.post",
    "httpx.get", "httpx.post", "urllib.request",
]
runtime_sources = list(pathlib.Path("app/runtime").rglob("*.py"))
check("runtime package has >= 12 modules", len(runtime_sources) >= 12)
for src_path in runtime_sources:
    text = src_path.read_text(encoding="utf-8", errors="replace").lower()
    for fb in forbidden:
        check(f"NO '{fb}' in {src_path.name}", fb.lower() not in text)
# Route file: runtime never imports execution/playwright
route_src = pathlib.Path("app/api/routes/runtime.py").read_text(encoding="utf-8", errors="replace").lower()
check("route no playwright",        "playwright" not in route_src)
check("route no subprocess",        "subprocess" not in route_src)
# Authorization read-only: context.py reads registry but never engine.evaluate
ctx_src = pathlib.Path("app/runtime/context.py").read_text(encoding="utf-8", errors="replace")
check("context reads auth registry", "authorization import registry" in ctx_src)
check("context never evaluates auth", "engine.evaluate" not in ctx_src and "auth_engine" not in ctx_src)
check("execution_ready is UI metadata only (documented)",
      "UI metadata" in ctx_src or "gates nothing" in ctx_src or "metadata only" in ctx_src.lower())
# main.py registers router
main_src = pathlib.Path("app/main.py").read_text(encoding="utf-8", errors="replace")
check("main registers runtime_router", "runtime_router" in main_src)
# mission schema + route integration
mission_schema_src = pathlib.Path("app/schemas/mission.py").read_text(encoding="utf-8", errors="replace")
check("mission schema has runtime field", "runtime:" in mission_schema_src)
mission_route_src = pathlib.Path("app/api/routes/mission.py").read_text(encoding="utf-8", errors="replace")
check("mission route builds runtime_summary", "runtime_summary" in mission_route_src)
# persistence disabled
persist_src = pathlib.Path("app/runtime/persistence.py").read_text(encoding="utf-8", errors="replace")
check("persistence flag default False", "RUNTIME_PERSISTENCE: bool = False" in persist_src)
section_summary("22. Safety — No Forbidden Patterns")

# ─────────────────────────────────────────────────────────────────────────────
# Final tally
# ─────────────────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*60}")
print(f"V8.9 VALIDATION: {PASS}/{total} checks passed")
if FAIL > 0:
    print(f"  FAILURES: {FAIL}")
else:
    print(f"  ALL CHECKS PASSED")
print(f"{'='*60}")
sys.exit(0 if FAIL == 0 else 1)
