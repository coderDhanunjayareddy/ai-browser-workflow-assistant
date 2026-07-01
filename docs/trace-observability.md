# M0.6 — Planner Observability & Execution Trace

**Status:** implemented. Diagnostics only — no planner/prompt/executor/validation/retry change.
**Goal:** after one benchmark run, answer *any* question about a step by opening one trace —
no source reading, no guessing, no manual reconstruction.

---

## 1. Guarantees

- **OFF by default.** Backend capture is gated by `TRACE_MODE`; benchmark capture by `--trace`.
- **Byte-identical when off.** With `TRACE_MODE` unset the `/analyze` HTTP response is unchanged
  and the only backend cost is one boolean check per call. With `--trace` off the benchmark uses
  the plain client and no recorder — identical results, identical browser behavior.
- **Never influences execution.** Everything is write-only observability. The planner makes the
  same decisions, the browser does the same thing, results are identical whether tracing is on or off.
- **No extra LLM calls.** Capture reuses the existing provider call.

---

## 2. Architecture (isolated layer)

```
BENCHMARK (backend/benchmark/trace/)                 BACKEND (backend/app/diagnostics/)
────────────────────────────────────                 ─────────────────────────────────
TracingAnalyzeClient  ── mints trace_id ──▶ /analyze  (X-Trace-Id header)
   │  logs request+parsed response                        │ route sets ContextVar (guarded)
   │                                                       ▼
   │                                      ai_service._call_openrouter_chat
   │                                        if TRACE_MODE: trace_sink.record_provider_exchange()
   │                                        → <TRACE_DIR>/backend/<trace_id>.json
   ▼                                                       (exact prompt + raw response + usage)
TaskRunner runs UNCHANGED ──▶ M0TaskResult (steps: executor/validation/artifacts)
   ▼
TraceRecorder.build_task(result, exchanges)
   merges: M0TaskResult.steps  +  client exchanges  +  backend/<trace_id>.json   (by trace_id + order)
   ▼
one StepTrace per step  →  trace_out/<run_id>/<task_id>/step_NNN.trace.json
   ▼
generate_viewer() → trace_out/<run_id>/<task_id>/viewer.html   (self-contained, offline)
```

**Correlation:** one `trace_id` per `/analyze` call links the benchmark exchange ↔ the backend
provider file. The same id appears in the step trace, the viewer, and (by convention path) the
screenshots/DOM snapshots for that step. One `trace_id` reconstructs one complete step.

**Why the TaskRunner is untouched:** tracing is a *wrapper* client injected by `run_suite` only
when `--trace` is set; the recorder reconstructs everything after the run from data the runner
already produced. This keeps the benchmark hot path and behavior exactly as-is.

---

## 3. What is captured (and what needs TRACE_MODE)

| Field | Source | Needs backend TRACE_MODE? |
|---|---|---|
| URL, title, DOM snapshot, screenshots, visible-text, element count/summary | benchmark | no |
| Exact request transmitted to `/analyze` (task + page_context + prior_steps) | benchmark | no |
| Parsed response: analysis, action, target, value, **reasoning, confidence** | benchmark (/analyze body) | no |
| Executor: locator strategy, selector used, attempts, duration, result, error | benchmark | no |
| Validation: result, reason, dom_changed, url_changed, criteria met | benchmark | no |
| Loop decision: continue / recovered / completed / stuck / failed / timeout / blocked + reason | benchmark | no |
| **Exact provider prompt** (assembled system+user messages) | backend | **yes** |
| **Raw provider response** (pre-parse text), finish_reason, token usage, latency | backend | **yes** |
| model, temperature, max_tokens, response_format | backend | **yes** |

Backend-internal fields are recorded as `available: false` / `null` with an explicit
`*_unavailable_reason` when `TRACE_MODE` is off — **never fabricated or reconstructed**.

---

## 4. Trace schema (`planner_trace_v1`)

One JSON object per step. Top-level: `schema_version, trace_id, run_id, task_id, session_id,
step_index`, then sections `observation, planner_input, provider_request, provider_response,
parsed_action, executor, validation, loop_decision`.

**Versioning / backward compatibility:** additive only. Never remove or repurpose a v1 key;
new versions add optional keys/sections and keep the same top-level shape; readers tolerate
unknown keys and missing optional sections. Unavailable fields are `null` + a reason, not omitted.

Builders live in `benchmark/trace/schema.py`; `SCHEMA_VERSION` is the single source of truth.

---

## 5. Storage layout

```
backend/
  .trace_sink/backend/<trace_id>.json        # backend: exact prompt + raw response (TRACE_MODE)
  benchmark/trace_out/<run_id>/<task_id>/
      step_000.trace.json ... step_NNN.trace.json
      index.json                             # status, failure_category, step file list
      viewer.html                            # self-contained viewer for this task
  benchmark/screenshots/<run_id>/<task_id>/step_NNN_{baseline,post_action}.png
  benchmark/dom_snapshots/<run_id>/<task_id>/step_NNN.json
```

`TRACE_DIR` (env or `settings.trace_dir`) overrides the default `.trace_sink` location; the
backend and benchmark resolve it identically so they share the directory on one host. Both
`trace_out/` and `.trace_sink/` are gitignored.

---

## 6. HTML viewer

`trace_out/<run_id>/<task_id>/viewer.html` — no external JS/CSS, opens offline:

- **Left:** step list, each dot coloured by loop decision.
- **Center:** observation (URL + before/after screenshots + elements the model saw) · provider
  request (exact assembled prompt) · raw provider response + parsed JSON · parsed action
  (type/target/value/reasoning/confidence + analysis).
- **Right:** executor (strategy, selector used, attempts, duration, result, browser error) ·
  validation (result, dom_changed, url_changed, criteria, reason) · loop decision + reason ·
  a clickable timeline of all steps.

Clicking any step immediately shows every artifact for it.

---

## 7. How to enable

Backend (separate terminal), enable capture of the exact prompt + raw text:

```bash
# Windows PowerShell:  $env:TRACE_MODE="true"
# mac/linux:           export TRACE_MODE=true
cd backend && python run.py
```

Benchmark run with tracing:

```bash
cd backend
python -m benchmark.m0_runner --suite nightly --site fixture_server \
    --executor playwright --backend http://localhost:8000 \
    --output benchmark/reports/diag.json --trace          # or env BENCHMARK_TRACE=true
# → open backend/benchmark/trace_out/<run_id>/<task_id>/viewer.html
```

If the backend is run **without** `TRACE_MODE`, tracing still works but the provider-request/raw
fields show "backend-internal; set TRACE_MODE=true to capture" — everything else is captured.

---

## 8. Performance

| Case | Cost |
|---|---|
| Tracing disabled (default) | recorder 0.000 ms/op; backend = one bool check per call |
| Tracing enabled | ~18 ms/task to build+write traces, ~17 ms/task to render the viewer — **per task, off the hot path**, dwarfed by browser + LLM latency |

Backend capture is one file write per `/analyze` call, only when `TRACE_MODE` is on.

---

## 9. Success-criteria map (question → where the answer lives in one trace)

| Question | Field(s) |
|---|---|
| Why did the LLM repeat? | `parsed_action.reasoning` + identical `parsed_action.target_selector` across steps + `observation.elements_summary` |
| Why wasn't page state recognized? | `observation` (no input values in `elements_summary`) + `validation.dom_changed` |
| Why wasn't validation satisfied? | `validation.validation_reason` + `success_criteria_satisfied` |
| Which selector actually got clicked? | `executor.selector_used` + `executor.locator_strategy` |
| What did the model see? | `planner_input.page_context_sent` + `observation.screenshot_before_path` + `provider_request.assembled_prompt` |
| What exactly did the model answer? | `provider_response.raw_text` (TRACE_MODE) + `provider_response.parsed_json` |
| Why did the loop continue / stop? | `loop_decision.decision` + `loop_decision.reason` |

---

## 10. Files

```
backend/app/core/config.py                 + trace_mode, trace_dir (additive)
backend/app/diagnostics/trace_sink.py      backend capture (gated, safe, write-only)
backend/app/api/routes/analyze.py          + X-Trace-Id header → ContextVar (guarded)
backend/app/services/ai_service.py         + guarded capture in _call_openrouter_chat
backend/benchmark/analyze_client.py        + optional trace_id → X-Trace-Id header
backend/benchmark/trace/schema.py          versioned schema builders
backend/benchmark/trace/tracing_client.py  wrapper: mint/forward trace_id, log exchanges
backend/benchmark/trace/recorder.py        merge sources → StepTrace files + index
backend/benchmark/trace/viewer.py          self-contained HTML viewer
backend/benchmark/trace/validate_trace.py  offline validation suite (22 checks)
backend/benchmark/trace/perf_trace.py      overhead benchmark
backend/benchmark/m0_runner.py             gated --trace wiring (additive)
backend/tests/benchmark/test_trace_*.py    unit tests
```
