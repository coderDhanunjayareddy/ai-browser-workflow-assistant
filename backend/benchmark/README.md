# M0 — Real Website Benchmark

The single source of truth for real-world browser task completion. It drives the **live**
`/analyze` loop (real Gemini reasoning) against real websites + local fixtures, in two
executor modes, and produces JSON / Markdown / HTML reports plus a locked baseline.

Design: `docs/benchmark-m0.md`. This README is the operator runbook.

---

## Install (one time)

```bash
cd backend
pip install -r requirements-benchmark.txt
playwright install chromium
```

`requirements-benchmark.txt` is dev/CI-only — production `requirements.txt` is untouched.

---

## Run the backend (separate terminal)

The benchmark calls a running backend. It needs a valid `GEMINI_API_KEY` (or OpenRouter)
in `backend/.env`.

```bash
cd backend
uvicorn app.main:app --port 8000
```

---

## Verify the harness first (offline, no API cost beyond fixtures)

```bash
# pure-Python checks — no browser, no network:
python -m benchmark.validate_m0      # 35 checks
python -m benchmark.perf_bench       # framework overhead
python -m pytest tests/benchmark -q  # 63 tests

# harness self-test — runs the local fixtures through a real browser + real /analyze.
# Asserts >=90% fixture completion and zero infrastructure errors before trusting any
# real-site numbers:
python -m benchmark.m0_runner --self-test
```

---

## Produce the first baseline (fixtures + no-auth real sites)

```bash
python -m benchmark.m0_runner \
    --suite nightly \
    --executor playwright \
    --backend http://localhost:8000 \
    --output benchmark/reports/m0-baseline.json \
    --headless

# repeat in synthetic mode to measure the execution-fidelity gap:
python -m benchmark.m0_runner --suite nightly --executor synthetic \
    --output benchmark/reports/m0-baseline-synthetic.json --headless
```

Auth-gated tasks (Gmail, Google Docs/Sheets, LinkedIn, Canva) **SKIP automatically** until
you record auth state (below). Open the generated `*.html` for the visual report.

Lock the baseline once you're happy with it (after ~3 low-variance runs):

```bash
python -m benchmark.m0_runner --suite nightly --executor playwright --update-baseline --headless
```

---

## Auth-gated sites (optional)

Record a session once, headed; it's saved to `benchmark/.playwright_state/{site}.json`
(gitignored — keep it in the team vault, refresh ~every 14 days):

```bash
python -m benchmark.record_auth --site google_com --url https://accounts.google.com
python -m benchmark.record_auth --site linkedin_com --url https://www.linkedin.com/login
```

Then add `--site` to run just that site, or run `nightly` to include all configured ones.

---

## CI gate

```bash
python -m benchmark.ci_check \
    --report benchmark/reports/m0.json \
    --baseline benchmark/baselines/nightly.json \
    --regression-threshold 0.10
```

Fails (exit 1) on: any fixture task not COMPLETED, any INFRASTRUCTURE error, or a
completion-rate regression beyond the threshold.

---

## Suites

| Suite | Tasks | When |
|---|---|---|
| `smoke` | 5 (3 fixtures + 2 no-auth) | every PR (~$0.20) |
| `nightly` | all 27 (auth tasks skip if unconfigured) | daily, both executor modes |
| `release` | all 27, run headed with `--no-auto-approve` | before a milestone release |

---

## What the two executor modes mean

- `--executor playwright` — trusted CDP input. **Upper bound**: a task that still fails here
  has a reasoning / grounding / planning problem (M1 won't fix it).
- `--executor synthetic` — injects the verbatim extension `executor_v2` synthetic events
  (`injected_scripts.js`). **Production reality**: what users experience today.

The per-tier gap between the two = the execution-fidelity problem M1 addresses.

Page observation **always** injects the verbatim extension `extractor_v2`, so the backend
receives the exact production DOM snapshot in both modes.

---

## Layout

```
benchmark/
  m0_runner.py        suite orchestrator + CLI + baseline
  m0_task_runner.py   the per-task observe->analyze->gate->execute->validate loop
  m0_executor.py      Driver + PlaywrightDriver (Mode A) + synthetic (Mode B) + capture
  m0_scenarios.py     the 27 task definitions
  m0_models.py        dataclasses + enums
  m0_metrics.py       aggregation, Wilson CI, cost, executor gap
  m0_report.py        JSON / Markdown / HTML
  criteria.py         success + failure criterion evaluation
  failure_classifier.py  one-failure-one-category decision tree
  website_profiles.py per-site auth / rate-limit / anti-bot config
  injected_scripts.js verbatim port of extractor_v2 + executor_v2 (Mode-B fidelity)
  analyze_client.py   /analyze HTTP client + risk gate
  fakes.py            test doubles (validation + tests only)
  ci_check.py         regression gate
  record_auth.py      auth-state recorder
  validate_m0.py      offline validation suite
  perf_bench.py       framework overhead benchmark
  suites/             smoke / nightly / release
  reports/            generated reports (gitignored)
  baselines/          locked baseline JSON (committed) — THE ONLY VALID BASELINE
  examples/           synthetic example reports (committed); tagged _EXAMPLE, never a baseline
```

## Planner tracing (diagnostics)

Add `--trace` to any run to record one complete StepTrace per step + a self-contained HTML
viewer under `benchmark/trace_out/<run_id>/<task_id>/viewer.html`. Start the backend with
`TRACE_MODE=true` to also capture the exact provider prompt + raw response. Off by default;
zero behavior change. Full docs: `docs/trace-observability.md`.

## What counts as a baseline

A baseline is **only** a report produced by `m0_runner` and written to
`benchmark/baselines/nightly.json`. Baseline resolution is a fixed path — `m0_runner` and
`ci_check` never search `reports/` or `examples/`, and both refuse any file tagged
`_EXAMPLE` (the synthetic demos in `examples/`). See `examples/README.md`.
