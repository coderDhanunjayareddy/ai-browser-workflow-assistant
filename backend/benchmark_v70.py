"""
benchmark_v70.py — V7.0 Live Browser Sync Layer performance benchmarks.

Targets:
  Event ingestion  (POST /browser/events)  < 5ms  p95
  Mission refresh  (MissionRefreshEngine)  <10ms  p95
  Trust refresh    (TrustRefreshEngine)    <10ms  p95
  Registry GET hit (BrowserEventRegistry)  < 1ms  p95
  Inspector        (BrowserEventInspector) <25ms  p95

Run: python benchmark_v70.py
"""
import time
import sys
import statistics
import uuid

_results: list[dict] = []
_failed_count = 0


def _bench(label: str, fn, n: int, target_ms: float) -> None:
    global _failed_count
    samples = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - t0) * 1000)
    samples.sort()
    p50 = statistics.median(samples)
    p95 = samples[int(n * 0.95)]
    p99 = samples[int(n * 0.99)]
    passed = p95 <= target_ms
    status = "PASS" if passed else "FAIL"
    if not passed:
        _failed_count += 1
    print(f"  {status}  {label}")
    print(f"         p50={p50:.2f}ms  p95={p95:.2f}ms  p99={p99:.2f}ms"
          f"  target=<{target_ms}ms")
    _results.append({"label": label, "p95": p95, "target_ms": target_ms, "passed": passed})


# ── Setup ─────────────────────────────────────────────────────────────────────
print("\nV7.0 Benchmark — setting up...")

from app.browser.models import BrowserEventType, make_event
import app.browser.registry as ev_reg
from app.browser import analytics as bra
from app.browser import timeline as tl
from app.browser.sync_service import LiveSyncService
from app.browser.mission_refresh import MissionRefreshEngine
from app.browser.trust_refresh import TrustRefreshEngine
from app.browser.inspector import BrowserEventInspector
from app.tabs import registry as tab_reg
from app.mission.models import Mission
import app.mission.store as ms
import app.trust.registry as trust_reg
from app.trust import analytics as trust_analytics
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

ev_reg._reset_for_testing()
bra._reset_for_testing()
tl._reset_for_testing()
tab_reg._reset_for_testing()
trust_reg._reset_for_testing()
trust_analytics._reset_for_testing()

def _mission() -> str:
    m = Mission(mission_id=str(uuid.uuid4()), title="Bench", objective="bench")
    ms.put(m)
    return m.mission_id

mid1 = _mission()
mid2 = _mission()


# ── 1. Event ingestion — model layer (no HTTP) ──────────────────────────────
print("\n[1] Event ingestion (model + registry, no HTTP)")
svc = LiveSyncService()

def _ingest():
    ev = make_event(BrowserEventType.tab_created, str(uuid.uuid4())[:8],
                    url="https://bench.com", mission_id=mid1)
    svc.process_event(ev)

_bench("Event ingestion (sync_service)", _ingest, n=500, target_ms=5)


# ── 2. Event ingestion — HTTP layer ───────────────────────────────────────────
print("\n[2] Event ingestion (POST /browser/events)")

def _http_ingest():
    client.post("/browser/events", json={
        "event_type": "TAB_CREATED",
        "tab_id":     str(uuid.uuid4())[:8],
        "url":        "https://http.com",
        "mission_id": mid1,
    })

_bench("POST /browser/events", _http_ingest, n=200, target_ms=10)


# ── 3. Registry GET hit ───────────────────────────────────────────────────────
print("\n[3] Registry GET (cached)")
ev_reg._reset_for_testing()
stored_ev = make_event(BrowserEventType.page_loaded, "t-bench", mission_id=mid1)
ev_reg.register(stored_ev)

def _reg_get():
    ev_reg.get(stored_ev.event_id)

_bench("Registry GET (cache hit)", _reg_get, n=2000, target_ms=1)


# ── 4. Mission refresh engine ─────────────────────────────────────────────────
print("\n[4] MissionRefreshEngine")
from app.browser.mission_refresh import _reset_for_testing as mr_reset
mr_reset()
engine = MissionRefreshEngine(cooldown_s=0)

def _mission_refresh():
    engine.refresh(mid2, "bench")

_bench("MissionRefreshEngine.refresh", _mission_refresh, n=100, target_ms=10)


# ── 5. Trust refresh engine ───────────────────────────────────────────────────
print("\n[5] TrustRefreshEngine")
trust_engine = TrustRefreshEngine()

def _trust_refresh():
    trust_engine.refresh(mid2, "bench")

_bench("TrustRefreshEngine.refresh", _trust_refresh, n=100, target_ms=10)


# ── 6. Inspector ──────────────────────────────────────────────────────────────
print("\n[6] BrowserEventInspector")
ev_reg._reset_for_testing()
tl._reset_for_testing()
for i in range(5):
    bev = make_event(BrowserEventType.tab_created, f"t-insp-{i}",
                     url="https://inspect.com", mission_id=mid2)
    ev_reg.register(bev)
    tl.append(mid2, bev)

inspector = BrowserEventInspector()

def _inspect():
    inspector.inspect(mid2)

_bench("BrowserEventInspector.inspect", _inspect, n=100, target_ms=25)


# ── 7. Analytics counter ──────────────────────────────────────────────────────
print("\n[7] Analytics counter (record_event)")

def _record():
    bra.record_event(BrowserEventType.url_changed)

_bench("BrowserEventAnalytics.record_event", _record, n=5000, target_ms=1)


# ── Summary ───────────────────────────────────────────────────────────────────
total   = len(_results)
passed  = sum(1 for r in _results if r["passed"])
print(f"\n{'='*55}")
print(f"V7.0 Benchmarks: {passed}/{total} passed", end="")
if _failed_count:
    print(f"  ({_failed_count} FAILED)")
    sys.exit(1)
else:
    print("  — ALL PASS")
