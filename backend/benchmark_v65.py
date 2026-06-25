"""
V6.5 Benchmark Suite — Trust Engine.

Targets:
  trust evaluation (classify + policy)  <  5ms p95
  mission trust analyze                 < 10ms p95
  workflow trust analyze                <  5ms p95
  tab trust analyze                     <  5ms p95
  registry cache hit                    <  1ms p95
  registry cache miss                   <  2ms p95
  action analyzer end-to-end            <  5ms p95
  REST /trust/evaluate                  < 15ms p95
  REST /trust/action                    < 15ms p95
  REST /trust/mission                   < 20ms p95
  REST /trust/inspect                   < 25ms p95

Run:
    python benchmark_v65.py
"""
import sys
import time
import uuid
import statistics


def p95(times: list[float]) -> float:
    s = sorted(times)
    idx = int(len(s) * 0.95)
    return s[min(idx, len(s) - 1)]


_results: list[tuple[str, float, float, bool]] = []


def section(title: str) -> None:
    print(f"\n-- {title} --")


def bench(label: str, target_ms: float, times_ms: list[float]) -> None:
    p = p95(times_ms)
    mean = statistics.mean(times_ms)
    ok   = p <= target_ms
    sym  = "+" if ok else "X"
    print(f"  [{sym}] {label}")
    print(f"        p95={p:.3f}ms  mean={mean:.3f}ms  target={target_ms}ms")
    _results.append((label, p, target_ms, ok))


def summary() -> None:
    total  = len(_results)
    passed = sum(1 for _, _, _, ok in _results if ok)
    failed = total - passed
    print(f"\n{'='*55}")
    print(f"BENCHMARK RESULT: {passed}/{total} under target, {failed} over")
    if failed:
        print("OVER TARGET:")
        for label, p, tgt, ok in _results:
            if not ok:
                print(f"  X {label}: p95={p:.3f}ms target={tgt}ms")
    sys.exit(0 if failed == 0 else 1)


REPS = 500

# ── Imports ───────────────────────────────────────────────────────────────────

from app.trust.models import RiskLevel, TargetType, make_evaluation
from app.trust.risk_classifier import RiskClassifier, classify
from app.trust.policy_engine import TrustPolicyEngine, evaluate
from app.trust.action_analyzer   import analyze as action_analyze
from app.trust.workflow_analyzer  import analyze as wf_analyze
from app.trust.tab_analyzer       import analyze as tab_analyze
from app.trust.mission_analyzer   import analyze as mission_analyze
import app.trust.registry  as trust_reg
from app.trust            import analytics as trust_analytics
trust_analytics._reset_for_testing()
trust_reg._reset_for_testing()

from fastapi.testclient import TestClient
from app.main import app
import app.mission.store as ms
from app.mission.models import Mission
client = TestClient(app)


# ── 1. RiskClassifier ─────────────────────────────────────────────────────────

section("1 - RiskClassifier")
clf = RiskClassifier()
t = []; [t.append((time.perf_counter(), clf.classify("read_page"), time.perf_counter())) for _ in range(REPS)]
bench("classify(read_page) — exact hit", 1.0, [(e - s)*1000 for s, _, e in t])

t2 = []; [t2.append((time.perf_counter(), clf.classify("confirm_purchase_xyz"), time.perf_counter())) for _ in range(REPS)]
bench("classify(unknown+substr) — fallback", 1.0, [(e - s)*1000 for s, _, e in t2])


# ── 2. TrustPolicyEngine ──────────────────────────────────────────────────────

section("2 - TrustPolicyEngine")
engine = TrustPolicyEngine()
t3 = []; [t3.append((time.perf_counter(), engine.evaluate("purchase"), time.perf_counter())) for _ in range(REPS)]
bench("evaluate(purchase) no context", 5.0, [(e - s)*1000 for s, _, e in t3])

t4 = []; [t4.append((time.perf_counter(),
                      engine.evaluate("click", workflow_type="purchase_workflow",
                                      blocker_count=2, missing_info_count=3),
                      time.perf_counter())) for _ in range(REPS)]
bench("evaluate(click) with all context", 5.0, [(e - s)*1000 for s, _, e in t4])


# ── 3. Action Analyzer ────────────────────────────────────────────────────────

section("3 - ActionTrustAnalyzer")
t5 = []; [t5.append((time.perf_counter(), action_analyze("purchase"), time.perf_counter())) for _ in range(REPS)]
bench("action_analyze(purchase)", 5.0, [(e - s)*1000 for s, _, e in t5])

t6 = []; [t6.append((time.perf_counter(), action_analyze("read_page"), time.perf_counter())) for _ in range(REPS)]
bench("action_analyze(read_page)", 5.0, [(e - s)*1000 for s, _, e in t6])


# ── 4. Workflow Analyzer ──────────────────────────────────────────────────────

section("4 - WorkflowTrustAnalyzer")
t7 = []; [t7.append((time.perf_counter(), wf_analyze("purchase_workflow"), time.perf_counter())) for _ in range(REPS)]
bench("wf_analyze(purchase_workflow)", 5.0, [(e - s)*1000 for s, _, e in t7])

t8 = []; [t8.append((time.perf_counter(),
                      wf_analyze("research_workflow", readiness_score=0.9, workflow_tab_present=True),
                      time.perf_counter())) for _ in range(REPS)]
bench("wf_analyze(research) full context", 5.0, [(e - s)*1000 for s, _, e in t8])


# ── 5. Tab Analyzer ───────────────────────────────────────────────────────────

section("5 - TabTrustAnalyzer")
ctx_5 = {
    "tab_count": 5,
    "tab_summaries": [
        {"tab_id": f"t{i}", "url": f"https://site{i}.com", "role": "RESEARCH",
         "state": "OPEN", "mission_id": "m1"}
        for i in range(5)
    ]
}
findings_5 = [{"code": "DUPLICATE_TABS", "severity": "INFO"}]
t9 = []; [t9.append((time.perf_counter(),
                      tab_analyze("m1", tab_context=ctx_5, tab_findings=findings_5),
                      time.perf_counter())) for _ in range(REPS)]
bench("tab_analyze 5 tabs + findings", 5.0, [(e - s)*1000 for s, _, e in t9])

t10 = []; [t10.append((time.perf_counter(), tab_analyze("m-none"), time.perf_counter())) for _ in range(REPS)]
bench("tab_analyze no tabs", 2.0, [(e - s)*1000 for s, _, e in t10])


# ── 6. Mission Analyzer ───────────────────────────────────────────────────────

section("6 - MissionTrustAnalyzer")
t11 = []; [t11.append((time.perf_counter(),
                        mission_analyze("m1", readiness_score=0.9,
                                        task_count=8, completed_task_count=6,
                                        failed_task_count=1, critical_blockers=1,
                                        tab_count=4, workflow_tab_present=True),
                        time.perf_counter())) for _ in range(REPS)]
bench("mission_analyze full context", 10.0, [(e - s)*1000 for s, _, e in t11])

t12 = []; [t12.append((time.perf_counter(), mission_analyze("m1"), time.perf_counter())) for _ in range(REPS)]
bench("mission_analyze minimal", 5.0, [(e - s)*1000 for s, _, e in t12])


# ── 7. Registry ───────────────────────────────────────────────────────────────

section("7 - TrustRegistry Cache")
trust_reg._reset_for_testing()
ev = make_evaluation(TargetType.action, "buy", 0.2, RiskLevel.critical, True, 0.9, "")
trust_reg.set_evaluation(ev)

t13 = []; [t13.append((time.perf_counter(), trust_reg.get(TargetType.action, "buy"), time.perf_counter())) for _ in range(REPS)]
bench("registry cache hit", 1.0, [(e - s)*1000 for s, _, e in t13])

t14 = []; [t14.append((time.perf_counter(), trust_reg.get(TargetType.action, "miss"), time.perf_counter())) for _ in range(REPS)]
bench("registry cache miss", 1.0, [(e - s)*1000 for s, _, e in t14])

t_set = []; [t_set.append((time.perf_counter(),
                            trust_reg.set_evaluation(
                                make_evaluation(TargetType.action, "k", 0.5, RiskLevel.medium, False, 0.9, "")),
                            time.perf_counter())) for _ in range(REPS)]
bench("registry set_evaluation", 2.0, [(e - s)*1000 for s, _, e in t_set])


# ── 8. REST API ───────────────────────────────────────────────────────────────

section("8 - REST API latency")
REST_REPS = 100

t_qe = []
for _ in range(REST_REPS):
    s = time.perf_counter()
    client.get("/trust/evaluate?action_type=purchase")
    t_qe.append((time.perf_counter() - s) * 1000)
bench("GET /trust/evaluate", 15.0, t_qe)

t_act = []
for _ in range(REST_REPS):
    s = time.perf_counter()
    client.post("/trust/action", json={"action_type": "click", "blocker_count": 1})
    t_act.append((time.perf_counter() - s) * 1000)
bench("POST /trust/action", 15.0, t_act)

t_wf = []
for _ in range(REST_REPS):
    s = time.perf_counter()
    client.post("/trust/workflow", json={"workflow_type": "research_workflow"})
    t_wf.append((time.perf_counter() - s) * 1000)
bench("POST /trust/workflow", 15.0, t_wf)

t_ms = []
for _ in range(REST_REPS):
    s = time.perf_counter()
    client.post("/trust/mission", json={
        "mission_id": "bench-m", "readiness_score": 0.8,
        "task_count": 4, "completed_task_count": 3,
    })
    t_ms.append((time.perf_counter() - s) * 1000)
bench("POST /trust/mission", 20.0, t_ms)

t_an = []
for _ in range(REST_REPS):
    s = time.perf_counter()
    client.get("/trust/analytics")
    t_an.append((time.perf_counter() - s) * 1000)
bench("GET /trust/analytics", 10.0, t_an)

m_b = Mission(mission_id=str(uuid.uuid4()), title="Bench", objective="test")
ms.put(m_b)
t_in = []
for _ in range(REST_REPS):
    s = time.perf_counter()
    client.get(f"/trust/inspect/{m_b.mission_id}")
    t_in.append((time.perf_counter() - s) * 1000)
bench("GET /trust/inspect/{id}", 25.0, t_in)

summary()
