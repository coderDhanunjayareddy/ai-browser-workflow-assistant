"""
V8.8 Execution Authorization Framework — Benchmark Suite.

Targets:
  B1. Authorization evaluation   < 1ms   (pure deterministic engine)
  B2. Registry hit               < 1ms   (in-memory TTL dict)
  B3. Readiness report           < 5ms   (non-blocking, graceful on missing services)
  B4. Inspector                  < 25ms  (full inspector with non-blocking calls)
  B5. HTTP POST /evaluate        < 15ms  (ASGI overhead included)
  B6. HTTP GET /authorization    < 10ms
  B7. Analytics GET              < 5ms
  B8. Timeline summary           < 1ms

Run: python benchmark_v88.py
"""
import sys
import time
import uuid
import statistics

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0

def bench(label: str, target_ms: float, fn, reps: int = 200) -> float:
    global PASS, FAIL
    times = []
    for _ in range(reps):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000)
    p50  = statistics.median(times)
    p95  = statistics.quantiles(times, n=20)[18]
    ok   = p95 <= target_ms
    tag  = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {label}")
    print(f"         p50={p50:.3f}ms  p95={p95:.3f}ms  target<{target_ms}ms")
    return p95


# ── Setup ─────────────────────────────────────────────────────────────────────
from app.governance.models import make_contract, ContractStatus
from app.authorization import engine as eng, registry as areg, timeline as tl, analytics as anal
from app.authorization import readiness as rdns, inspector as insp
from app.authorization.models import make_authorization

areg._reset_for_testing(); tl._reset_for_testing(); anal._reset_for_testing()
from app.governance import registry as gov_reg; gov_reg._reset_for_testing()

now = time.time()
contract = make_contract(
    str(uuid.uuid4()), True, "tester", now,
    "TRUST_ENGINE", str(uuid.uuid4()), "HIGH",
    mission_id="m-bench", ttl_seconds=3600,
)
gov_reg.add(contract)

auth_sample = eng.evaluate(contract)
areg.add(auth_sample)

print("\n=== V8.8 Execution Authorization — Benchmarks ===\n")

# ── B1. Authorization evaluation ──────────────────────────────────────────────
print("[B1] Authorization Evaluation (engine)")
bench("engine.evaluate() — ACTIVE contract",    1.0,  lambda: eng.evaluate(contract))

# ── B2. Registry hit ──────────────────────────────────────────────────────────
print("\n[B2] Registry Hit")
auth_id = auth_sample.authorization_id
bench("registry.get(auth_id)",                  1.0,  lambda: areg.get(auth_id))
bench("registry.get_for_contract(ctr_id)",      1.0,  lambda: areg.get_for_contract(contract.contract_id))
bench("registry.count()",                       1.0,  lambda: areg.count())

# ── B3. Readiness report ──────────────────────────────────────────────────────
print("\n[B3] Readiness Report")
bench("readiness.evaluate(mission_id)",         5.0,  lambda: rdns.evaluate("m-bench"), reps=100)

# ── B4. Inspector ─────────────────────────────────────────────────────────────
print("\n[B4] Inspector")
bench("inspector.inspect(mission_id)",          25.0, lambda: insp.inspect("m-bench"), reps=100)

# ── B5-B7. HTTP layer ─────────────────────────────────────────────────────────
print("\n[B5-B7] HTTP Layer")
from fastapi.testclient import TestClient
from app.main import app
http_client = TestClient(app)

bench("POST /authorization/evaluate/{id}",    15.0,
      lambda: http_client.post(f"/authorization/evaluate/{contract.contract_id}"),
      reps=50)

bench("GET /authorization",                   10.0,
      lambda: http_client.get("/authorization"),
      reps=100)

bench("GET /authorization/analytics",          5.0,
      lambda: http_client.get("/authorization/analytics"),
      reps=100)

# ── B8. Timeline ──────────────────────────────────────────────────────────────
print("\n[B8] Timeline")
for _ in range(20):
    tl.record(str(uuid.uuid4()), "created", mission_id="m-bench")

bench("timeline.summary(mission_id)",           1.0, lambda: tl.summary("m-bench"))
bench("timeline.get(mission_id)",               1.0, lambda: tl.get("m-bench"))

# ── Summary ───────────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*50}")
print(f"V8.8 BENCHMARKS: {PASS}/{total} pass")
if FAIL > 0:
    print(f"  FAILURES: {FAIL}")
else:
    print(f"  ALL BENCHMARKS PASS")
print(f"{'='*50}")
sys.exit(0 if FAIL == 0 else 1)
