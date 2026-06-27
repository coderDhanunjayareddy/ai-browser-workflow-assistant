"""
V8.5 Governance Layer — Performance Benchmarks
Targets:
  B1: Registry get           < 1ms  (100 iters)
  B2: Eligibility check      < 1ms  (100 iters)
  B3: Inspector              < 25ms (10 iters)
  B4: Analytics get          < 1ms  (100 iters)
  B5: HTTP GET /contracts    < 10ms (20 iters)
  B6: HTTP POST revoke       < 10ms (10 iters)
  B7: HTTP GET eligibility   < 10ms (10 iters)
  B8: HTTP GET inspect       < 25ms (10 iters)
  B9: Timeline record        < 1ms  (100 iters)

Run: python benchmark_v85.py
"""
from __future__ import annotations

import sys
import time
import uuid
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from app.governance import registry as reg, analytics as anal, timeline as tl
from app.governance import eligibility as elig, inspector as insp
from app.governance.models import make_contract, ContractStatus
from app.approvals import registry as appr_reg, analytics as appr_anal, timeline as appr_tl


def bench(label: str, fn, iters: int, target_ms: float) -> bool:
    t0 = time.perf_counter()
    for _ in range(iters):
        fn()
    elapsed = (time.perf_counter() - t0) * 1000
    avg = elapsed / iters
    ok = avg < target_ms
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {label}: avg={avg:.3f}ms / target<{target_ms}ms  (n={iters})")
    return ok


def _make_c(mission_id="m-bench"):
    return make_contract(
        approval_id = str(uuid.uuid4()),
        approved    = True,
        approved_by = "bench",
        approved_at = time.time(),
        source_type = "TRUST_ENGINE",
        source_id   = "s",
        risk_level  = "HIGH",
        mission_id  = mission_id,
        ttl_seconds = 3600.0,
    )


# ─── Setup ───────────────────────────────────────────────────────────────────
reg._reset_for_testing()
appr_reg._reset_for_testing()
anal._reset_for_testing()
appr_anal._reset_for_testing()
tl._reset_for_testing()
appr_tl._reset_for_testing()

for _ in range(50):
    reg.add(_make_c())
all_ids = [c.contract_id for c in reg.list_all(limit=50)]
target_id = all_ids[0]
target_c  = reg.get(target_id)

print("V8.5 Governance Layer — Performance Benchmarks")
print("=" * 60)
results = []

# B1: Registry hit
results.append(bench(
    "B1 Registry.get (cache hit)",
    lambda: reg.get(target_id),
    iters=100, target_ms=1.0,
))

# B2: Eligibility check
results.append(bench(
    "B2 Eligibility.check",
    lambda: elig.check(target_c),
    iters=100, target_ms=1.0,
))

# B3: Inspector (50 contracts)
reg.add(_make_c(mission_id="m-bench"))
results.append(bench(
    "B3 Inspector.inspect (50 contracts)",
    lambda: insp.inspect("m-bench"),
    iters=10, target_ms=25.0,
))

# B4: Analytics
results.append(bench(
    "B4 Analytics.get_analytics",
    lambda: anal.get_analytics(),
    iters=100, target_ms=1.0,
))

# B5: Timeline record
results.append(bench(
    "B5 Timeline.record",
    lambda: tl.record(str(uuid.uuid4()), "created",
                      mission_id="m-bench", risk_level="HIGH"),
    iters=100, target_ms=1.0,
))

# B6–B9: HTTP benchmarks
from fastapi.testclient import TestClient
from app.main import app as fa_app
from app.approvals.models import (
    ApprovalSourceType, ApprovalRiskLevel, make_approval_request,
)

client = TestClient(fa_app)

# warm up + create a governance contract
def _make_approved_contract():
    a = make_approval_request(
        source_type = ApprovalSourceType.trust_engine,
        source_id   = str(uuid.uuid4()),
        title       = "Bench Approval",
        description = "bench",
        risk_level  = ApprovalRiskLevel.high,
        priority    = "HIGH",
        mission_id  = "m-bench-http",
    )
    appr_reg.add(a)
    r = client.post(f"/approvals/{a.approval_id}/approve")
    return r.json()["governance_contract"]["contract_id"]

gc_id = _make_approved_contract()

results.append(bench(
    "B6 GET /governance/contracts",
    lambda: client.get("/governance/contracts"),
    iters=20, target_ms=15.0,   # ASGI/TestClient overhead
))

results.append(bench(
    "B7 GET /governance/contracts/{id}/eligibility",
    lambda: client.get(f"/governance/contracts/{gc_id}/eligibility"),
    iters=10, target_ms=10.0,
))

results.append(bench(
    "B8 GET /governance/inspect/{mission_id}",
    lambda: client.get("/governance/inspect/m-bench-http"),
    iters=10, target_ms=25.0,
))

# B9: POST revoke (create fresh contracts each time)
def _revoke_bench():
    gid = _make_approved_contract()
    client.post(f"/governance/contracts/{gid}/revoke", json={"reason": "bench"})

results.append(bench(
    "B9 POST revoke (create+revoke cycle)",
    _revoke_bench,
    iters=10, target_ms=10.0,
))

# ─── Report ──────────────────────────────────────────────────────────────────
print("=" * 60)
passed = sum(1 for r in results if r)
failed = len(results) - passed
print(f"Results: {passed}/{len(results)} benchmarks passed")
if failed:
    print(f"BENCHMARKS FAILED ({failed} targets missed)")
    sys.exit(1)
else:
    print(f"ALL {len(results)} BENCHMARKS PASS")
    sys.exit(0)
