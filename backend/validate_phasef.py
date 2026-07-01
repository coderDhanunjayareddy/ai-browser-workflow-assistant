"""
Phase F — Certification & Reliability — Validation Suite (deterministic, browser-free).

Validates the certification framework, fixtures, scenarios, reliability rollup, failure
catalog, report, workflow trace, the AmbiguousLocator reliability fix, REST surface,
additivity, and a static safety scan. All deterministic (mock-mode certification + WI
over fixtures); no real browser required.

Run: python validate_phasef.py
"""
import sys
import pathlib

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PASS = 0
FAIL = 0
SECTIONS = []

def section(name):
    global PASS, FAIL
    SECTIONS.append((name, PASS, FAIL))
    print(f"\n[{name}]")

def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL: {label}")

def summ(name):
    prev = SECTIONS[-1]
    print(f"  -> {PASS - prev[1]} pass, {FAIL - prev[2]} fail")


from app.certification import (
    models, fixtures, scenarios, reliability, failure_catalog, report, trace, runner,
)
from app.certification.models import (
    ScenarioCategory, OutcomeStatus, CriterionKind, WorkflowOutcome, CertificationResult,
)
from app.certification.reliability import percentile
from app.certification.failure_catalog import Reproducibility, ResolutionStatus
from app.execution_gateway.browser import failure_classes as fc
from app.execution_gateway.browser.failure_classes import FailureCategory, FailureSeverity, RecoveryAction
from app.execution_gateway import registry as ereg, analytics as ganal, timeline as gtl, audit
from app.execution_planning import registry as plan_reg
from app.authorization import registry as auth_reg
from app.mission import store as mission_store
from app.execution_gateway.browser import monitor as mon, metrics as met, exec_timeline as etl


def reset_all():
    for m in [ereg, ganal, gtl, audit, plan_reg, auth_reg, mission_store, mon, met, etl,
              reliability, failure_catalog]:
        m._reset_for_testing()


# ─────────────────────────────────────────────────────────────────────────────
section("1. Package Structure")
for f in ["__init__", "models", "fixtures", "scenarios", "reliability", "failure_catalog",
          "trace", "runner", "report"]:
    check(f"module {f}.py", pathlib.Path(f"app/certification/{f}.py").exists())
check("REST route", pathlib.Path("app/api/routes/certification.py").exists())
summ("1. Package Structure")

# ─────────────────────────────────────────────────────────────────────────────
section("2. Fixtures")
EXPECTED = ["/login", "/register", "/dashboard", "/crud", "/search", "/upload", "/download",
            "/pagination", "/modal", "/multistep", "/scroll", "/nav", "/tabs", "/accordion",
            "/dynamic", "/toast", "/confirm", "/dragdrop"]
check("18 fixtures", len(fixtures.FIXTURES) == 18)
from app.website_intelligence import analyzer as wi
for path in EXPECTED:
    check(f"fixture {path} present", path in fixtures.FIXTURES)
    html = fixtures.FIXTURES[path]
    check(f"fixture {path} html non-empty", len(html) > 50)
    res = wi.analyze_html(html, title=path)
    check(f"fixture {path} WI page root", res.page.root.type.value == "PAGE")
    check(f"fixture {path} WI deterministic", wi.analyze_html(html).page.type_counts == res.page.type_counts)
    check(f"fixture {path} has nodes", res.stats["dom_nodes"] > 0)
    check(f"fixture {path} lookup", fixtures.fixture_html(path) == html)
SEM = {"/login": "FORM", "/register": "FORM", "/crud": "TABLE", "/nav": "NAVIGATION",
       "/tabs": "TABS", "/accordion": "ACCORDION", "/pagination": "PAGINATION", "/upload": "UPLOAD",
       "/download": "DOWNLOAD", "/dashboard": "DASHBOARD", "/confirm": "DIALOG", "/modal": "DIALOG",
       "/search": "SEARCH_BAR", "/dragdrop": "CARD"}
for path, stype in SEM.items():
    tc = wi.analyze_html(fixtures.FIXTURES[path]).page.type_counts
    check(f"fixture {path} semantic {stype}", tc.get(stype, 0) >= 1)
check("fixture_names sorted", fixtures.fixture_names() == sorted(fixtures.FIXTURES.keys()))
check("download body bytes", isinstance(fixtures.DOWNLOAD_BODY, bytes) and len(fixtures.DOWNLOAD_BODY) > 0)
summ("2. Fixtures")

# ─────────────────────────────────────────────────────────────────────────────
section("3. Fixture Server")
srv = fixtures.FixtureServer().start()
try:
    import urllib.request
    check("server base_url", srv.base_url.startswith("http://127.0.0.1:"))
    for path in EXPECTED:
        with urllib.request.urlopen(srv.base_url + path, timeout=5) as r:
            body = r.read().decode()
        check(f"server serves {path}", "<body>" in body and len(body) > 50)
    with urllib.request.urlopen(srv.base_url + "/download-file", timeout=5) as r:
        check("server download-file", r.read() == fixtures.DOWNLOAD_BODY)
    with urllib.request.urlopen(srv.base_url + "/unknown-path", timeout=5) as r:
        check("server fallback", r.status == 200)
finally:
    srv.stop()
summ("3. Fixture Server")

# ─────────────────────────────────────────────────────────────────────────────
section("4. Scenarios")
scs = scenarios.build_scenarios()
check("scenario count >= 22", len(scs) >= 22)
ids = [s.scenario_id for s in scs]
check("unique ids", len(ids) == len(set(ids)))
for s in scs:
    check(f"{s.scenario_id} has build_steps", s.build_steps is not None)
    steps = s.build_steps("http://x")
    check(f"{s.scenario_id} steps non-empty", len(steps) >= 1)
    check(f"{s.scenario_id} first step navigate", steps[0].action_type.value == "NAVIGATE")
    check(f"{s.scenario_id} criteria", len(s.success_criteria) >= 1)
    check(f"{s.scenario_id} fixture served", s.fixture in fixtures.FIXTURES)
    check(f"{s.scenario_id} category enum", isinstance(s.category, ScenarioCategory))
    d = s.to_dict()
    for k in ["scenario_id", "name", "website", "workflow", "category", "fixture",
              "success_criteria", "known_limitations", "expect_failure"]:
        check(f"{s.scenario_id} dict {k}", k in d)
    for st in steps:
        check(f"{s.scenario_id} step has action_type", hasattr(st, "action_type"))
        check(f"{s.scenario_id} step has parameters", isinstance(st.parameters, dict))
REQUIRED_CATS = [ScenarioCategory.form_submit, ScenarioCategory.search, ScenarioCategory.filter,
                 ScenarioCategory.table_edit, ScenarioCategory.upload, ScenarioCategory.download,
                 ScenarioCategory.navigation, ScenarioCategory.dialog, ScenarioCategory.recovery,
                 ScenarioCategory.resume, ScenarioCategory.pagination, ScenarioCategory.multistep,
                 ScenarioCategory.tabs, ScenarioCategory.accordion, ScenarioCategory.dynamic_loading,
                 ScenarioCategory.toast, ScenarioCategory.infinite_scroll, ScenarioCategory.drag_drop]
cats = {s.category for s in scs}
for c in REQUIRED_CATS:
    check(f"category covered {c.value}", c in cats)
summ("4. Scenarios")

# ─────────────────────────────────────────────────────────────────────────────
section("5. Reliability — percentile")
check("empty", percentile([], 50) == 0.0)
check("single", percentile([7], 99) == 7.0)
check("median even", percentile([1, 2, 3, 4], 50) == 2.5)
check("p90", percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) == 9.1)
check("p0 min", percentile([5, 1, 9], 0) == 1.0)
check("p100 max", percentile([5, 1, 9], 100) == 9.0)
# monotonic non-decreasing across percentiles
vals = [3.0, 1.0, 4.0, 1.5, 5.0, 9.0, 2.0, 6.0]
pcts = [percentile(vals, p) for p in range(0, 101, 10)]
for i in range(1, len(pcts)):
    check(f"percentile monotonic {i}", pcts[i] >= pcts[i - 1])
summ("5. Reliability — percentile")

# ─────────────────────────────────────────────────────────────────────────────
section("6. Reliability — rollup")
reliability._reset_for_testing()
for i in range(20):
    reliability.record_workflow(WorkflowOutcome(f"s{i}", "FORM_SUBMIT" if i % 2 else "SEARCH",
                                                "app", i < 16, float(i)))
m = reliability.metrics()
check("workflows_total", m["workflows_total"] == 20)
check("workflows_passed", m["workflows_passed"] == 16)
check("success_rate", m["workflow_success_rate"] == 0.8)
check("failed", m["workflows_failed"] == 4)
check("duration keys", set(m["duration_ms"].keys()) == {"p50", "p95", "p99", "max", "avg"})
check("category FORM", "FORM_SUBMIT" in m["category_success"])
check("category SEARCH", "SEARCH" in m["category_success"])
check("category total", m["category_success"]["SEARCH"]["total"] == 10)
check("step_metrics merged", "step_metrics" in m)
reliability.record_semantic_latency(1.5)
reliability.record_semantic_latency(3.0)
check("semantic samples", reliability.metrics()["semantic_analysis_ms"]["samples"] == 2)
reliability._reset_for_testing()
check("reset clears", reliability.metrics()["workflows_total"] == 0)
summ("6. Reliability — rollup")

# ─────────────────────────────────────────────────────────────────────────────
section("7. Failure Catalog")
failure_catalog._reset_for_testing()
r1 = failure_catalog.record(category="FORM", website="a", workflow="w", seen_at=100.0)
check("first record once", r1.reproducibility == Reproducibility.once)
check("occurrences 1", r1.occurrences == 1)
r2 = failure_catalog.record(category="FORM", website="a", workflow="w", seen_at=200.0)
check("dedup same key", len(failure_catalog.list_all()) == 1)
check("occurrences 2", r2.occurrences == 2)
check("first_seen kept", r2.first_seen == 100.0)
check("last_seen updated", r2.last_seen == 200.0)
check("promoted intermittent", r2.reproducibility == Reproducibility.intermittent)
failure_catalog.record(category="FORM", website="a", workflow="w", seen_at=300.0)
check("promoted always", failure_catalog.list_all()[0].reproducibility == Reproducibility.always)
failure_catalog.record(category="B", website="a", workflow="w", seen_at=1.0)
s = failure_catalog.summary()
check("distinct 2", s["total_distinct"] == 2)
check("occurrences total", s["total_occurrences"] == 4)
for k in ["total_distinct", "total_occurrences", "by_category", "by_resolution", "records"]:
    check(f"summary {k}", k in s)
check("catalog id format", failure_catalog.list_all()[0].catalog_id.startswith("fail-"))
got = failure_catalog.get(failure_catalog.list_all()[0].catalog_id)
check("get by id", got is not None)
failure_catalog._reset_for_testing()
check("catalog reset", failure_catalog.summary()["total_distinct"] == 0)
summ("7. Failure Catalog")

# ─────────────────────────────────────────────────────────────────────────────
section("8. AmbiguousLocator reliability fix")
check("category exists", any(c.value == "AmbiguousLocator" for c in FailureCategory))
amb = FailureCategory.ambiguous_locator
check("profile permanent", fc.profile_for(amb).severity == FailureSeverity.permanent)
check("profile not retryable", fc.profile_for(amb).retryable is False)
check("profile recovery none", fc.profile_for(amb).recommended_recovery == (RecoveryAction.none,))
check("in PERMANENT set", amb in fc.PERMANENT_CATEGORIES)
check("not in RETRYABLE set", amb not in fc.RETRYABLE_CATEGORIES)
# ambiguous classification (strict uniqueness / strict mode violation, >1 match)
AMBIG = [
    "strict uniqueness failed: text='Edit' matched 2 elements (not unique)",
    "strict uniqueness failed: role='button' matched 5 elements",
    "strict mode violation: locator resolved to 3 elements",
    "strict mode violation: get_by_text('x') resolved to 2 elements",
    "the locator is not unique; matched 4 elements",
]
for msg in AMBIG:
    a = fc.classify_failure(Exception(msg), phase="click")
    check(f"ambiguous: {msg[:40]}", a.category == FailureCategory.ambiguous_locator)
    check(f"ambiguous permanent: {msg[:30]}", a.profile.retryable is False)
# zero-match strict failure is NOT ambiguous (it is genuinely missing -> recoverable)
ZERO = [
    "strict uniqueness failed: id='x' matched 0 elements (no node found)",
]
for msg in ZERO:
    a = fc.classify_failure(Exception(msg), phase="click")
    check(f"zero-match not ambiguous: {msg[:30]}", a.category == FailureCategory.element_not_found)
    check(f"zero-match retryable: {msg[:30]}", a.profile.retryable is True)
# unrelated messages unaffected (regression: no over-match)
UNAFFECTED = [
    ("no node found", FailureCategory.element_not_found),
    ("element is hidden", FailureCategory.element_hidden),
    ("target closed", FailureCategory.page_crash),
    ("Timeout 30000ms exceeded", FailureCategory.transient_timeout),
]
for msg, exp in UNAFFECTED:
    check(f"unaffected {msg[:24]}", fc.classify_failure(Exception(msg), phase="").category == exp)
check("category count 19", len(FailureCategory) == 19)
summ("8. AmbiguousLocator reliability fix")

# ─────────────────────────────────────────────────────────────────────────────
section("9. Mock-mode certification (pipeline)")
reset_all()
results = runner.certify_all(scs, base_url="", real_browser=False, seen_at=1000.0)
check("all scenarios run", len(results) == len(scs))
for r in results:
    check(f"{r.scenario_id} passed", r.status == OutcomeStatus.passed)
    check(f"{r.scenario_id} has exec id", r.execution_id is not None)
    check(f"{r.scenario_id} criteria evaluated", len(r.criteria) == len(
        next(s for s in scs if s.scenario_id == r.scenario_id).success_criteria))
    d = r.to_dict()
    for k in ["scenario_id", "status", "passed", "execution_state", "completed_steps",
              "total_steps", "duration_ms", "criteria", "real_browser"]:
        check(f"{r.scenario_id} dict {k}", k in d)
relm = reliability.metrics()
check("reliability total", relm["workflows_total"] == len(scs))
check("reliability success 1.0", relm["workflow_success_rate"] == 1.0)
check("semantic latencies recorded", relm["semantic_analysis_ms"]["samples"] >= 10)
summ("9. Mock-mode certification (pipeline)")

# ─────────────────────────────────────────────────────────────────────────────
section("10. Determinism")
def cert_states():
    reset_all()
    rs = runner.certify_all(scs, base_url="", real_browser=False, seen_at=1.0)
    return [(r.scenario_id, r.status.value, r.completed_steps,
             tuple(c.passed for c in r.criteria)) for r in rs]
base = cert_states()
for run_i in range(2):
    again = cert_states()
    for i, (a, b) in enumerate(zip(base, again)):
        check(f"deterministic run{run_i} scenario{i}", a == b)
summ("10. Determinism")

# ─────────────────────────────────────────────────────────────────────────────
section("11. Report")
reset_all()
results = runner.certify_all(scs, base_url="", real_browser=False, seen_at=1.0)
rep = report.build_report(results, scenarios=scs, mode="mock")
for k in ["mode", "scenarios_total", "supported_count", "unsupported_count", "pass_rate",
          "supported", "unsupported", "known_limitations", "observed_failures", "reliability",
          "recommendations"]:
    check(f"report {k}", k in rep)
check("report total", rep["scenarios_total"] == len(scs))
check("report pass_rate 1.0", rep["pass_rate"] == 1.0)
check("report supported all", rep["supported_count"] == len(scs))
check("report has limitations", len(rep["known_limitations"]) >= 3)
check("report recommendations", len(rep["recommendations"]) >= 1)
md = report.render_markdown(rep)
check("markdown header", "Certification Report" in md)
check("markdown reliability", "Reliability" in md)
check("markdown scenarios", "Supported scenarios" in md)
summ("11. Report")

# ─────────────────────────────────────────────────────────────────────────────
section("12. Trace")
check("no trace unknown", trace.has_trace("no-exec-xyz") is False)
snap = trace.semantic_snapshot_of(fixtures.FIXTURES["/login"], title="login")
check("snapshot not none", snap is not None)
check("snapshot form", snap["page"]["type_counts"].get("FORM", 0) >= 1)
check("snapshot keys", set(["page", "forms", "registry"]).issubset(snap.keys()))
summ("12. Trace")

# ─────────────────────────────────────────────────────────────────────────────
section("13. REST endpoints")
from fastapi.testclient import TestClient
from app.main import app
client = TestClient(app)
routes = {r.path for r in app.routes}
for p in ["/certification/scenarios", "/certification/reliability", "/certification/failures",
          "/certification/run", "/certification/report", "/certification/workflow-trace/{execution_id}"]:
    check(f"route {p}", p in routes)
reset_all()
r = client.get("/certification/scenarios")
check("scenarios 200", r.status_code == 200)
check("scenarios count", r.json()["count"] == len(scs))
r = client.post("/certification/run")
check("run 200", r.status_code == 200)
check("run mock mode", r.json()["mode"] == "mock")
check("run pass_rate", r.json()["pass_rate"] == 1.0)
check("reliability 200", client.get("/certification/reliability").status_code == 200)
check("failures 200", client.get("/certification/failures").status_code == 200)
check("report 200", client.get("/certification/report").status_code == 200)
check("trace 404 unknown", client.get("/certification/workflow-trace/none").status_code == 404)
# additivity: prior routes intact
for p in ["/gateway/browser/diagnostics/{execution_id}", "/website-intelligence/analyze",
          "/mission/{mission_id}/inspect", "/gateway/browser/metrics"]:
    check(f"existing route {p}", p in routes)
summ("13. REST endpoints")

# ─────────────────────────────────────────────────────────────────────────────
section("14. Static Safety (no AI/Vision/OCR in certification pkg)")
forbidden = ["import openai", "from openai", "import anthropic", "import torch",
             "import transformers", "import cv2", "pytesseract", "import sklearn", "import numpy",
             "embedding(", "llm_", "vision_model(", ".ocr(", "self_heal(", "import random", "random."]
cert_files = list(pathlib.Path("app/certification").rglob("*.py"))
check("cert pkg >= 9 modules", len(cert_files) >= 9)
for src in cert_files:
    text = src.read_text(encoding="utf-8", errors="replace").lower()
    for fb in forbidden:
        check(f"NO '{fb}' in {src.name}", fb.lower() not in text)
summ("14. Static Safety")

# ─────────────────────────────────────────────────────────────────────────────
section("15. Stress / invariants")
for n in range(1, 51):
    reliability._reset_for_testing()
    passes = (n * 3) % 7 != 0
    for i in range(n):
        reliability.record_workflow(WorkflowOutcome(f"s{i}", "C", "app", (i % 4 != 0), float(i % 10)))
    m = reliability.metrics()
    expected_pass = sum(1 for i in range(n) if i % 4 != 0)
    check(f"stress {n} total", m["workflows_total"] == n)
    check(f"stress {n} passed", m["workflows_passed"] == expected_pass)
    check(f"stress {n} rate range", 0.0 <= m["workflow_success_rate"] <= 1.0)
    check(f"stress {n} p50<=p95", m["duration_ms"]["p50"] <= m["duration_ms"]["p95"] + 1e-9)
    check(f"stress {n} p95<=p99", m["duration_ms"]["p95"] <= m["duration_ms"]["p99"] + 1e-9)
    check(f"stress {n} category", m["category_success"]["C"]["total"] == n)
reliability._reset_for_testing()
summ("15. Stress / invariants")

# ── Final tally ───────────────────────────────────────────────────────────────
total = PASS + FAIL
print(f"\n{'='*62}")
print(f"PHASE F VALIDATION: {PASS}/{total} checks passed")
print("  ALL CHECKS PASSED" if FAIL == 0 else f"  FAILURES: {FAIL}")
print(f"{'='*62}")
sys.exit(0 if FAIL == 0 else 1)
