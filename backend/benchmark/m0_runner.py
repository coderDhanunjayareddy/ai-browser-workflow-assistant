"""
M0 — Benchmark runner (suite orchestrator + CLI).

Loads a suite, runs each task through the TaskRunner against a freshly launched Chromium,
aggregates the results, writes JSON/Markdown/HTML reports, and compares against the locked
baseline. Real-site tasks call the LIVE /analyze backend (real Gemini); fixture tasks are
served by the offline FixtureServer.

Usage:
  python -m benchmark.m0_runner --suite smoke --executor playwright \\
      --backend http://localhost:8000 --output benchmark/reports/m0.json --headless

  python -m benchmark.m0_runner --self-test          # offline harness self-check (needs Playwright)
  python -m benchmark.m0_runner --suite nightly --executor playwright --update-baseline
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Optional

from benchmark import m0_scenarios, m0_metrics, m0_report, website_profiles
from benchmark.m0_models import M0TaskDefinition, M0TaskResult, TaskStatus
from benchmark.analyze_client import AnalyzeClient
from benchmark.m0_task_runner import TaskRunner

_HERE = os.path.dirname(os.path.abspath(__file__))
SUITES_DIR = os.path.join(_HERE, "suites")
REPORTS_DIR = os.path.join(_HERE, "reports")
ARTIFACTS_DIR = _HERE
AUTH_DIR = os.path.join(_HERE, ".playwright_state")
SECRETS_FILE = os.path.join(_HERE, ".benchmark_secrets")
ASSETS_DIR = os.path.join(_HERE, "assets")
UPLOAD_FILE = os.path.join(ASSETS_DIR, "benchmark_test.txt")
BASELINE_FILE = os.path.join(_HERE, "baselines", "nightly.json")
TRACE_OUT_DIR = os.path.join(_HERE, "trace_out")


# ── suite loading ─────────────────────────────────────────────────────────────

def load_suite(name: str) -> dict:
    path = os.path.join(SUITES_DIR, f"{name}.yaml")
    if not os.path.exists(path):
        raise FileNotFoundError(f"suite not found: {path}")
    import yaml
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def select_tasks(suite: dict, *, site: Optional[str], task: Optional[str]) -> list[M0TaskDefinition]:
    all_tasks = m0_scenarios.build_m0_scenarios()
    explicit = suite.get("task_ids")
    if explicit:
        chosen = [t for t in all_tasks if t.task_id in explicit]
    else:
        chosen = []
        for t in all_tasks:
            prof = website_profiles.get_profile(t.site_id)
            is_auth = bool(prof and prof.auth_required)
            if t.is_fixture and suite.get("include_fixtures", True):
                chosen.append(t)
            elif (not t.is_fixture) and (not is_auth) and suite.get("include_no_auth", True):
                chosen.append(t)
            elif is_auth and suite.get("include_auth", False):
                chosen.append(t)
    if site:
        chosen = [t for t in chosen if t.site_id == site]
    if task:
        chosen = [t for t in chosen if t.task_id == task]
    return chosen


# ── setup helpers ─────────────────────────────────────────────────────────────

def _ensure_upload_file() -> None:
    os.makedirs(ASSETS_DIR, exist_ok=True)
    if not os.path.exists(UPLOAD_FILE):
        with open(UPLOAD_FILE, "w", encoding="utf-8") as f:
            f.write("benchmark upload payload\n")


def _auth_state_path(task: M0TaskDefinition) -> Optional[str]:
    f = task.preconditions.auth_state_file
    if not f:
        return None
    return os.path.join(AUTH_DIR, f)


def _should_skip(task: M0TaskDefinition) -> Optional[str]:
    if task.skip_reason:
        return task.skip_reason
    if task.preconditions.auth_required:
        path = _auth_state_path(task)
        if not path or not os.path.exists(path):
            return f"auth state not configured ({task.preconditions.auth_state_file})"
    return None


# ── core run ──────────────────────────────────────────────────────────────────

def run_suite(*, suite_name: str, executor: str, backend: str, headless: bool,
              site: Optional[str] = None, task: Optional[str] = None,
              auto_approve: bool = True, run_id: Optional[str] = None,
              trace: bool = False) -> tuple[list[M0TaskResult], dict]:
    from benchmark.m0_executor import PlaywrightDriver  # lazy (needs playwright)

    suite = load_suite(suite_name)
    tasks = select_tasks(suite, site=site, task=task)
    run_id = run_id or f"m0-{suite_name}-{int(time.time())}"
    client = AnalyzeClient(backend)
    _ensure_upload_file()

    # M0.6 diagnostics: opt-in. When off, everything below is bypassed and the run is
    # identical (plain client, no recorder). When on, wrap the client to mint/forward a
    # trace_id per call and assemble a StepTrace + HTML viewer per task afterwards.
    recorder = None
    if trace:
        from benchmark.trace.tracing_client import TracingAnalyzeClient
        from benchmark.trace.recorder import TraceRecorder
        from app.diagnostics.trace_sink import resolve_trace_dir
        client = TracingAnalyzeClient(client)
        recorder = TraceRecorder(enabled=True, artifacts_dir=ARTIFACTS_DIR, out_dir=TRACE_OUT_DIR,
                                 trace_dir=resolve_trace_dir(), run_id=run_id)

    # one fixture server for all fixture tasks
    fixture_base = ""
    fixture_server = None
    if any(t.is_fixture for t in tasks):
        from app.certification.fixtures import FixtureServer
        fixture_server = FixtureServer().start()
        fixture_base = fixture_server.base_url

    results: list[M0TaskResult] = []
    last_site: Optional[str] = None
    started = time.time()
    try:
        for t in tasks:
            skip = _should_skip(t)
            if skip:
                results.append(_skipped(t, executor, skip))
                _log(f"SKIP {t.task_id}: {skip}")
                continue

            # rate-limit delay between consecutive tasks on the same real site
            prof = website_profiles.get_profile(t.site_id)
            if prof and prof.rate_limit_delay_ms and last_site == t.site_id:
                time.sleep(prof.rate_limit_delay_ms / 1000.0)
            last_site = t.site_id

            start_url = t.start_url.replace("{fixture_base}", fixture_base)
            t_run = _with_url(t, start_url)
            mode = t.executor_override or executor

            driver = None
            try:
                driver = PlaywrightDriver.launch(
                    headless=headless, storage_state=_auth_state_path(t), upload_file=UPLOAD_FILE)
                runner = TaskRunner(driver=driver, client=client, executor_mode=mode,
                                    run_id=run_id, artifacts_dir=ARTIFACTS_DIR,
                                    auto_approve=auto_approve)
                res = runner.run(t_run)
            except Exception as e:  # runner-level / launch failure -> ERROR, keep going
                res = _errored(t, mode, e)
            finally:
                if driver is not None:
                    try:
                        driver.close()
                    except Exception:
                        pass
            results.append(res)
            _log(f"{res.status.value:9s} {t.task_id} ({res.steps_taken} steps, "
                 f"{res.duration_ms:.0f}ms){' ['+res.failure_category+']' if res.failure_category else ''}")

            # M0.6: assemble the per-step trace + HTML viewer for this task (gated; safe).
            if recorder is not None:
                try:
                    sess = f"benchmark_{t.task_id}_{run_id}"
                    recorder.build_task(res, client.exchanges_for(sess))
                    from benchmark.trace.viewer import generate_viewer
                    generate_viewer(out_dir=TRACE_OUT_DIR, run_id=run_id, task_id=t.task_id,
                                    artifacts_dir=ARTIFACTS_DIR)
                except Exception:
                    pass
    finally:
        if fixture_server is not None:
            fixture_server.stop()

    m0_metrics.feed_reliability(results)
    duration_s = round(time.time() - started, 1)
    meta = {
        "run_id": run_id, "suite": suite_name, "executor_mode": executor,
        "backend_url": backend, "duration_s": duration_s,
        "tasks_in_suite": len(tasks),
    }
    return results, meta


# ── reporting + baseline ──────────────────────────────────────────────────────

def write_reports(results: list[M0TaskResult], meta: dict, *, executor: str,
                  output: str, baseline: Optional[dict]) -> dict:
    report = m0_report.build_report(meta=meta, results=results, executor_mode=executor,
                                    baseline=baseline)
    os.makedirs(os.path.dirname(os.path.abspath(output)), exist_ok=True)
    base, _ = os.path.splitext(output)
    with open(base + ".json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    with open(base + ".md", "w", encoding="utf-8") as f:
        f.write(m0_report.render_markdown(report))
    with open(base + ".html", "w", encoding="utf-8") as f:
        f.write(m0_report.render_html(report))
    return report


def load_baseline() -> Optional[dict]:
    # The ONLY valid baseline is the m0_runner-produced file under benchmark/baselines/.
    # Fixed path by design — never globs reports/ or examples/, so synthetic example
    # reports can never be mistaken for a baseline.
    if os.path.exists(BASELINE_FILE):
        with open(BASELINE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if is_example_report(data):
            raise ValueError(
                f"{BASELINE_FILE} is a synthetic EXAMPLE report, not a real baseline. "
                "Produce a baseline with m0_runner (see docs/run-first-baseline.md).")
        return data
    return None


def is_example_report(data: dict) -> bool:
    """True if a report dict is a synthetic example, not a real m0_runner baseline."""
    return bool(data.get("_EXAMPLE")) or bool(data.get("meta", {}).get("example"))


def save_baseline(report: dict) -> None:
    os.makedirs(os.path.dirname(BASELINE_FILE), exist_ok=True)
    with open(BASELINE_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)


# ── small helpers ─────────────────────────────────────────────────────────────

def _with_url(task: M0TaskDefinition, url: str) -> M0TaskDefinition:
    import copy
    t = copy.copy(task)
    t.start_url = url
    return t


def _skipped(task: M0TaskDefinition, executor: str, reason: str) -> M0TaskResult:
    r = M0TaskResult(task_id=task.task_id, website=task.website, difficulty=task.difficulty.value,
                     category=task.category.value, executor_mode=executor,
                     expect_failure=task.expect_failure, status=TaskStatus.skipped)
    r.failure_detail = reason
    return r


def _errored(task: M0TaskDefinition, executor: str, exc: Exception) -> M0TaskResult:
    r = M0TaskResult(task_id=task.task_id, website=task.website, difficulty=task.difficulty.value,
                     category=task.category.value, executor_mode=executor,
                     expect_failure=task.expect_failure, status=TaskStatus.error)
    r.failure_category = "INFRASTRUCTURE"
    r.failure_detail = f"{type(exc).__name__}: {str(exc)[:200]}"
    return r


def _log(msg: str) -> None:
    print(f"[m0] {msg}", flush=True)


# ── CLI ─────────────────────────────────────────────────────────────────────--

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="M0 Real Website Benchmark runner")
    p.add_argument("--suite", default="smoke", help="suite name in benchmark/suites/")
    p.add_argument("--executor", default="playwright", choices=["playwright", "synthetic"])
    p.add_argument("--backend", default=os.environ.get("BENCHMARK_BACKEND", "http://localhost:8000"))
    p.add_argument("--output", default=os.path.join(REPORTS_DIR, "m0-latest.json"))
    p.add_argument("--headless", action="store_true")
    p.add_argument("--site", default=None, help="only run tasks for this site_id")
    p.add_argument("--task", default=None, help="only run this task_id")
    p.add_argument("--no-auto-approve", dest="auto_approve", action="store_false")
    p.add_argument("--update-baseline", action="store_true",
                   help="write this run's report as the locked baseline")
    p.add_argument("--self-test", action="store_true",
                   help="run the offline fixture self-test and assert harness health")
    p.add_argument("--trace", action="store_true",
                   default=os.environ.get("BENCHMARK_TRACE", "").lower() in ("1", "true", "yes"),
                   help="record a full planner trace + HTML viewer per step (needs backend "
                        "TRACE_MODE=true for the exact prompt/raw response). No behavior change.")
    args = p.parse_args(argv)

    if args.self_test:
        return _run_self_test(args.backend, headless=True)

    results, meta = run_suite(
        suite_name=args.suite, executor=args.executor, backend=args.backend,
        headless=args.headless, site=args.site, task=args.task, auto_approve=args.auto_approve,
        trace=args.trace)
    report = write_reports(results, meta, executor=args.executor, output=args.output,
                           baseline=load_baseline())
    s = report["summary"]
    _log(f"DONE completion={s['completion_rate']:.1%} "
         f"({s['tasks_completed']}/{s['tasks_counted']} counted) cost=${s['estimated_cost_usd']:.2f}")
    if args.trace:
        _log(f"trace + viewers -> {os.path.join(TRACE_OUT_DIR, meta['run_id'])}"
             f" (open <task_id>/viewer.html)")
    if args.update_baseline:
        save_baseline(report)
        _log(f"baseline updated -> {BASELINE_FILE}")
    return 0


def _run_self_test(backend: str, *, headless: bool) -> int:
    """Run only fixture tasks; assert >=90% completion and zero INFRASTRUCTURE errors."""
    results, meta = run_suite(suite_name="smoke", executor="playwright", backend=backend,
                              headless=headless, site="fixture_server",
                              run_id=f"selftest-{int(time.time())}")
    counted = [r for r in results if r.counts_toward_completion]
    completed = sum(1 for r in counted if r.is_completed)
    rate = completed / len(counted) if counted else 0.0
    infra = sum(1 for r in results if r.failure_category == "INFRASTRUCTURE")
    _log(f"SELF-TEST completion={rate:.0%} infra_errors={infra}")
    ok = rate >= 0.90 and infra == 0
    _log("SELF-TEST " + ("PASS" if ok else "FAIL — harness unhealthy, do NOT collect real-site data"))
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
