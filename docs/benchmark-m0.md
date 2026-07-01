# M0 — Real Website Benchmark: Complete Implementation Program

**Date:** 2026-06-29  
**Status:** Design document. No code. Implementation program for another engineer.  
**Sole objective:** Establish the first real-world task completion baseline so that every future engineering decision can be judged against a measured number, not a guess.  
**Prerequisite reading:** `docs/architecture-alignment.md` (motivation), `docs/architecture-reconciliation.md` (subsystem map).

---

## Why This Document Exists

The project has zero measurement of real-world task completion on real websites. Phase F certification runs real Chromium but only against 24 synthetic local HTML fixtures on `127.0.0.1` with stable `data-testid`s, asserting 100% pass — a number that is meaningless for the stated goal of completing arbitrary browser tasks on real sites.

Every engineering decision made before M0 completes — every subsystem added, every optimization made, every claim about reliability — was made without knowing whether the agent can actually complete real tasks. That stops here.

**M0 is not a feature. It is the measurement instrument. Without it, M1–M4 are guesses.**

---

## A Critical Design Choice: What the Benchmark Actually Measures

The M0 benchmark uses Playwright's trusted CDP input for execution rather than `executor_v2.ts`'s synthetic DOM events. This is intentional and must be understood:

- **`executor_v2.ts` uses untrusted synthetic events** (`element.click()`, manual `value` set, dispatched `input`/`change`) that React/Vue controlled inputs, `isTrusted`-gated handlers, and custom widgets routinely reject or ignore.
- **Playwright uses CDP-level trusted input** (`Input.dispatchMouseEvent`, real focus, native interactions) that frameworks cannot distinguish from real user input.

Running M0 with Playwright's executor intentionally **isolates reasoning failures from execution failures**:

- A task that fails EVEN WITH Playwright's trusted input → the failure is in AI reasoning, grounding, planning, or perception. M1 (better driver) will NOT fix it.
- A task that SUCCEEDS with Playwright but fails in production → the failure is execution fidelity. M1 (CDP trusted driver in extension) will fix it.

**The benchmark establishes two numbers simultaneously:**

| Mode | Executor | What it measures |
|---|---|---|
| `--executor playwright` (default) | Playwright trusted input | Upper bound: AI reasoning quality, planning, grounding |
| `--executor synthetic` | extractor_v2.ts logic injected via eval | Current production reality: what users actually experience |

The gap between the two modes quantifies the execution fidelity problem that M1 addresses.

Both modes call the **real `/analyze` endpoint** (real Gemini/OpenRouter call). Neither mode uses mocks for the AI reasoning.

---

## Part 1 — Full Lifecycle: User Starts Benchmark → Dashboard

### Invocation

The benchmark operator runs:

```
python -m benchmark.m0_runner \
    --suite smoke \
    --executor playwright \
    --backend http://localhost:8000 \
    --output reports/m0-$(date +%Y%m%d).json \
    --headless
```

Suites: `smoke` (5 tasks, fast), `nightly` (all tasks, headless), `release` (all tasks, headed, human approval enabled).

### Full Step-by-Step Lifecycle

```
OPERATOR
   │
   ▼ runs benchmark CLI
BENCHMARK RUNNER (new: benchmark/m0_runner.py)
   │
   ├── 1. LOAD CONFIGURATION
   │     • reads backend URL from --backend (or BENCHMARK_BACKEND env)
   │     • reads credentials from .benchmark_secrets (never committed)
   │     • reads suite definition from benchmark/suites/{suite}.yaml
   │     • validates all task definitions before running any
   │
   ├── 2. FOR EACH TASK IN SUITE (sequential per site, parallel across sites optional)
   │     │
   │     ├── 2a. SETUP
   │     │     • launch Playwright Chromium (headless or headed per --headless flag)
   │     │     • restore auth state if task.preconditions.auth_required
   │     │       (load from .playwright_state/{task.site_id}.json, or run login sub-flow)
   │     │     • navigate to task.start_url
   │     │     • wait for network-idle (timeout: task.initial_load_timeout_ms)
   │     │     • take baseline screenshot → store in ScreenshotStore
   │     │     • start TimelineRecorder for this task
   │     │
   │     ├── 2b. LOOP (until: completed | timeout | step_budget | blocked | error)
   │     │     │
   │     │     ├── OBSERVE
   │     │     │     • inject extractor_v2 JS via page.evaluate() → DOM snapshot
   │     │     │       (exact same extraction payload as the real extension)
   │     │     │     • take screenshot → store in ScreenshotStore
   │     │     │     • record DOM snapshot → DOMSnapshotStore
   │     │     │     • wait for visual stability (≤200ms after last DOM mutation)
   │     │     │
   │     │     ├── ANALYZE (AI call)
   │     │     │     • POST /analyze to the backend with:
   │     │     │         - task: task.goal
   │     │     │         - page_context: extracted DOM snapshot
   │     │     │         - prior_steps: accumulated step history
   │     │     │         - session_id: benchmark_{task_id}_{run_id}
   │     │     │     • record: request_timestamp, response_timestamp
   │     │     │     • record: token counts from response headers (if available)
   │     │     │     • parse SuggestedAction from response
   │     │     │     • if action.type == "task_complete": exit loop → VALIDATE
   │     │     │
   │     │     ├── GATE (trust + approval)
   │     │     │     • classify action risk using trust rules:
   │     │     │         - "safe": auto-approve (navigate, click non-submit, type, extract)
   │     │     │         - "caution": auto-approve in smoke/nightly; human in release
   │     │     │         - "danger": always require human approval
   │     │     │           (danger actions: pay, purchase, delete-account, send-email,
   │     │     │            confirm-booking, place-order — same list as production)
   │     │     │     • if human approval required and --auto-approve: skip task → BLOCKED
   │     │     │     • record: approval_mode, action_risk, human_intervention (bool)
   │     │     │
   │     │     ├── EXECUTE
   │     │     │     • executor mode A (playwright):
   │     │     │         - resolve locator: try ranked strategies in order
   │     │     │           (accessibility_name > aria_label > data-testid > text > css > xpath)
   │     │     │         - execute via Playwright trusted API
   │     │     │         - record: locator_strategy_used, locator_attempt_count
   │     │     │     • executor mode B (synthetic):
   │     │     │         - inject executor_v2.ts logic via page.evaluate()
   │     │     │         - execute via synthetic events (exact production behavior)
   │     │     │     • record: execution_start, execution_end, action_type
   │     │     │     • on execution error: classify → failure_catalog.record()
   │     │     │
   │     │     ├── WAIT
   │     │     │     • wait for network-idle (max 3s)
   │     │     │     • wait for visual stability (max 1s)
   │     │     │     • take post-action screenshot → ScreenshotStore
   │     │     │
   │     │     ├── VALIDATE (step-level)
   │     │     │     • check step.expected_post_condition if defined:
   │     │     │         - url_matches: current URL matches pattern
   │     │     │         - dom_contains: element selector present in DOM
   │     │     │         - text_present: text appears on page
   │     │     │     • record: step_validation_passed (bool), validation_detail
   │     │     │     • on validation failure: increment recovery_attempts
   │     │     │         - if recovery_attempts < task.retry_budget: retry step with note
   │     │     │         - else: classify failure → exit loop
   │     │     │
   │     │     └── LOOP CONTROL
   │     │           • if steps_taken >= task.max_steps: timeout → record "max_steps_reached"
   │     │           • if elapsed > task.timeout_ms: timeout → record "timeout"
   │     │           • if CAPTCHA detected: blocked → record "captcha"
   │     │           • else: continue to next OBSERVE
   │     │
   │     ├── 2c. VALIDATE TASK COMPLETION
   │     │     • evaluate all task.success_criteria (reuse CriterionKind)
   │     │     • evaluate all task.failure_criteria (if any fail → task failed)
   │     │     • determine task status: completed | failed | timeout | blocked | error
   │     │     • collect expected_artifacts:
   │     │         - screenshots (all steps)
   │     │         - DOM snapshots (all steps)
   │     │         - extracted data (if task expects it)
   │     │         - timeline JSON
   │     │
   │     ├── 2d. RECORD
   │     │     • reliability.record_workflow(WorkflowOutcome)
   │     │     • failure_catalog.record() if task failed
   │     │     • MetricsCollector.record_task(TaskMetrics)
   │     │     • TimelineRecorder.finalize()
   │     │
   │     └── 2e. TEARDOWN
   │           • close Playwright browser (or keep open for next task on same site)
   │           • clear auth state if task requested cleanup
   │
   ├── 3. AGGREGATE METRICS
   │     • per-task, per-site, per-difficulty, per-category rollups
   │     • compute primary metrics (completion rate, step success, human interventions)
   │     • compute secondary metrics (latency, cost, token counts)
   │     • compute failure distribution across taxonomy categories
   │
   ├── 4. GENERATE REPORTS
   │     • JSON report → reports/m0-{run_id}.json
   │     • Markdown report → reports/m0-{run_id}.md
   │     • HTML report → reports/m0-{run_id}.html
   │
   └── 5. UPDATE DASHBOARD
         • copy HTML report to docs/benchmark-dashboard.html (or static site)
         • write baseline.json (first run only) or compare.json (subsequent runs)
         • emit regression warnings if completion rate dropped > threshold
```

### The Loop Invariant

Every iteration of the inner loop (2b) corresponds to one step of the task: one DOM observation, one AI reasoning call, one action, one validation. The harness tracks all of these. At the end, the combination of all steps is the task.

---

## Part 2 — Benchmark Architecture

### Component Map

```
benchmark/
  m0_runner.py          ← main loop orchestrator (new)
  m0_task_runner.py     ← per-task execution engine (new)
  m0_scenarios.py       ← real-site task definitions (new)
  m0_models.py          ← extended data models (new, extends certification/models.py)
  m0_executor.py        ← playwright/synthetic execution adapters (new)
  m0_metrics.py         ← MetricsCollector (new, reuses certification/reliability.py)
  m0_report.py          ← HTML/MD/JSON report generator (new, extends certification/report.py)
  website_profiles.py   ← per-site configuration (auth, rate limits, anti-bot) (new)
  suites/
    smoke.yaml          ← 5 quick tasks for PR checks
    nightly.yaml        ← all 24+ tasks
    release.yaml        ← all tasks + human approval enabled
  screenshots/          ← per-run screenshot storage (gitignored)
  dom_snapshots/        ← per-run DOM snapshot storage (gitignored)
  timelines/            ← per-run timeline JSON (gitignored)
  reports/              ← generated reports (committed on release runs)
  baseline.json         ← the first M0 run result (the fixed baseline)

Reused from certification/:
  certification/models.py         ← CertificationScenario, CertificationResult (extend, not fork)
  certification/reliability.py    ← ReliabilityRegister (reuse directly)
  certification/failure_catalog.py← FailureCatalog (reuse directly)
  certification/trace.py          ← workflow_trace (reuse directly)
```

---

### Component 1: BenchmarkRunner (`m0_runner.py`)

**Responsibility:** Orchestrate the benchmark run end-to-end. Load suite, iterate tasks, collect results, generate reports.

**Inputs:**
- Suite definition (YAML file from `suites/`)
- CLI arguments: `--suite`, `--executor`, `--backend`, `--headless`, `--output`, `--site` (filter), `--task` (filter), `--auto-approve`
- Environment: `BENCHMARK_BACKEND`, `BENCHMARK_SECRETS_PATH`, `GEMINI_API_KEY` (read by backend)

**Outputs:**
- List of `M0TaskResult` objects
- JSON/MD/HTML reports
- Updated baseline.json or comparison with previous baseline

**Key behaviors:**
1. Validates all task definitions BEFORE running any task (fail fast).
2. Runs tasks for the same site in sequence (to avoid rate limiting); optionally runs different sites in parallel.
3. On unrecoverable runner error (browser crash, backend down), records the task as ERROR and continues to the next.
4. After the full suite, emits a `run_summary` with overall completion rate and regression delta from baseline.

---

### Component 2: TaskRunner (`m0_task_runner.py`)

**Responsibility:** Drive the complete observe→analyze→approve→execute→validate loop for one task until completion, timeout, or failure.

**Inputs:**
- One `M0TaskDefinition`
- Backend URL
- Playwright `Page` object (already navigated to start URL)
- Auth state already restored

**Outputs:**
- One `M0TaskResult` (status, steps taken, metrics, artifacts)

**Key behaviors:**
1. **Loop budget enforcement**: hard stop at `task.max_steps` or `task.timeout_ms`, whichever comes first.
2. **Step-level recovery**: if a step fails validation and `task.retry_budget > 0`, retry that step once with a note to the AI that the previous action didn't work.
3. **Completion detection**: the loop exits when the AI returns `action_type: "task_complete"`, OR when all `task.success_criteria` evaluate to true, OR on budget exhaustion.
4. **CAPTCHA detection**: before each OBSERVE, check for known CAPTCHA indicators in DOM (aria-label contains "captcha", element with id matching "cf-challenge", etc.). On detection: record BLOCKED status, skip task.
5. **Loop stability guard**: if the last 3 extracted DOM snapshots are byte-identical AND the AI suggested the same action, record STUCK status and exit.

---

### Component 3: Task Definitions (`m0_scenarios.py`)

**Responsibility:** Declare every benchmark task as a structured Python object (`M0TaskDefinition`). This is the "benchmark dataset." See Part 4 for the full suite.

**Inputs:** None (declarative).

**Outputs:** `list[M0TaskDefinition]` via `build_m0_scenarios()`.

**Key constraint:** Tasks are pure data. No control flow, no browser calls, no AI calls. The runner drives them; the task only declares what, not how.

---

### Component 4: Task Definition Schema (`m0_models.py`)

**Responsibility:** Extend `CertificationScenario` with real-site-specific fields. Extend `SuccessCriterion` with real-site criterion kinds. Add `M0TaskResult` as the output record.

Full schema is defined in Part 3.

---

### Component 5: ExecutionAdapter (`m0_executor.py`)

**Responsibility:** Receive a `SuggestedAction` from `/analyze` and execute it against a live Playwright `Page`. Two modes.

**Inputs:** `SuggestedAction` (same schema as production), Playwright `Page`

**Outputs:** `ExecutionResult` (success bool, locator_strategy_used, error_detail, duration_ms)

**Mode A — Playwright trusted (default):**
1. Resolve locator by ranked strategy:
   - Try accessibility_name (role + name): `page.get_by_role(role, name=name).first`
   - Try aria_label: `page.get_by_label(label).first`
   - Try data-testid: `page.get_by_test_id(testid).first`
   - Try text match: `page.get_by_text(text, exact=False).first`
   - Try CSS selector: `page.locator(css).first`
   - Try XPath: `page.locator(xpath).first`
2. Execute via Playwright API: `click()`, `fill()`, `select_option()`, `press()`, `navigate()`.
3. Record which strategy resolved.
4. On failure of all strategies: record GROUNDING_FAILURE, return ExecutionResult(success=False).

**Mode B — Synthetic (production-equivalent):**
1. Inject `executor_v2.ts` compiled JS into the page via `page.evaluate()`.
2. Call `window.__extensionExecute__(action)` within the page context.
3. Record the result.
4. On failure: record EXECUTION_FAILURE, return ExecutionResult(success=False).

**The locator resolution order in Mode A exactly follows `locator_engine.LocatorRanker`'s strategy ranking.** This validates that LocatorRanker's rank order is correct before it is wired into production in M1.

---

### Component 6: PageCapture (`m0_executor.py`, observation function)

**Responsibility:** Extract the current page state in the same format that the extension's `extractor_v2.ts` produces. Called at the start of every loop iteration.

**Inputs:** Playwright `Page`

**Outputs:** `PageContext` (same Pydantic schema as `POST /analyze` expects: interactive_elements, content_blocks, url, title, visible_text)

**How:**
1. Inject `extractor_v2.ts` compiled JS via `page.evaluate()` (or a minimal Python re-implementation of the extraction logic).
2. Execute `window.__extensionExtract__()` to get the raw extraction result.
3. Parse into a `PageContext` matching the existing schema.
4. Take a screenshot with `page.screenshot(full_page=False)` and attach it to the snapshot for vision use (M3 territory, but capture it now so baselines exist).

**Why inject the extension's extractor:** this produces the EXACT same DOM representation that the backend receives in production. If we used a different extractor, we'd be testing a different system. The extraction must be faithful to production.

---

### Component 7: MetricsCollector (`m0_metrics.py`)

**Responsibility:** Record per-step and per-task metrics. Compute aggregate statistics after the suite.

**Inputs:** Events emitted by TaskRunner at each step (observe, analyze, execute, validate).

**Outputs:** Structured metrics dict consumed by ReportGenerator.

**Reuse:** Delegates to `certification/reliability.py` for `record_workflow()`. Extends with additional per-step counters.

Tracked per task:
- `steps_taken`, `steps_successful`, `steps_failed`
- `human_interventions` (count of danger/caution actions requiring human approval)
- `recoveries_attempted`, `recoveries_successful`
- `validations_passed`, `validations_failed`
- `ai_calls` (count of `/analyze` calls)
- `total_tokens` (prompt + completion, from response metadata)
- `total_cost_usd` (estimated from token counts + model rates)
- `observe_time_ms` (sum), `analyze_time_ms` (sum), `execute_time_ms` (sum)
- `locator_strategies_used` (dict: strategy → count)
- `failure_layer` (which taxonomy category caused the task to fail, if failed)

---

### Component 8: FailureClassifier (`m0_metrics.py`, classification function)

**Responsibility:** At the point a task step fails, classify the failure into exactly one taxonomy category. See Part 6 for the full taxonomy.

**Inputs:** error information (exception type, error message, step, action, DOM state at failure time)

**Outputs:** `FailureCategory` enum value

**Key principle:** One failure, one category. The category must be decided at failure time with the available evidence. If ambiguous, prefer the most specific resolvable category (Grounding > Planning > Execution > Validation).

---

### Component 9: ScreenshotStore (`benchmark/screenshots/`)

**Responsibility:** Save every screenshot taken during the benchmark. Make them available for offline analysis and HTML reports.

**Storage format:** `screenshots/{run_id}/{task_id}/step_{n:03d}_{event}.png`

Events: `baseline`, `pre_action`, `post_action`, `final`, `failure`.

**Retention:** Screenshots are NOT committed to git. They are stored locally and referenced by relative path in the HTML report. A `--upload-screenshots` flag can push them to S3/GCS for sharing.

---

### Component 10: DOMSnapshotStore (`benchmark/dom_snapshots/`)

**Responsibility:** Save the extracted DOM state at each loop iteration for offline analysis.

**Storage format:** `dom_snapshots/{run_id}/{task_id}/step_{n:03d}.json`

Content: the full `PageContext` JSON as sent to `/analyze`.

**Why store DOM snapshots:** This makes failures reproducible without re-running the browser. Any failed step can be replayed by calling `/analyze` with the saved snapshot.

---

### Component 11: TimelineRecorder (`certification/trace.py` + extension)

**Responsibility:** Record a chronological event timeline for each task. Reuses the existing `exec_timeline` infrastructure where possible.

**Events recorded:**
- `task_start`, `task_end`, `task_complete`, `task_failed`, `task_timeout`, `task_blocked`
- `step_start(n)`, `step_observe`, `step_analyze_request`, `step_analyze_response`, `step_gate`, `step_execute`, `step_validate`, `step_end(n)`
- `recovery_attempt`, `recovery_success`, `recovery_failure`
- `human_intervention_required`, `human_intervention_granted`, `human_intervention_denied`
- `captcha_detected`, `stuck_detected`

All events include: `timestamp_ms`, `elapsed_ms` from task start, `detail` dict.

---

### Component 12: ReportGenerator (`m0_report.py`)

**Responsibility:** Transform the collection of `M0TaskResult` objects into HTML, Markdown, and JSON reports.

Extends `certification/report.py` with real-site-specific formatting. See Part 7 for full report specs.

---

### Component 13: WebsiteProfile (`benchmark/website_profiles.py`)

**Responsibility:** Store per-site operational configuration that is not task-specific.

For each site:
- `site_id`: short slug (e.g., `amazon_in`, `github_com`)
- `base_url`: the canonical URL
- `auth_required`: bool
- `auth_strategy`: `session_state` | `credential_login` | `none`
- `auth_state_file`: relative path to saved Playwright storage state (for `session_state` mode)
- `credentials_key`: key into `.benchmark_secrets` file (for `credential_login` mode)
- `rate_limit_delay_ms`: minimum delay between tasks on this site
- `captcha_probability`: `low` | `medium` | `high`
- `anti_bot`: bool (whether Cloudflare/Akamai/Datadome is present)
- `recording_mode`: `live` | `recorded` (recorded = use saved session replay instead of live site)
- `known_blocks`: list of URL patterns where the site typically blocks automation

---

## Part 3 — Task Definition Schema

### M0TaskDefinition (extends CertificationScenario)

The following schema defines a benchmark task. Every field is mandatory unless marked optional.

| Field | Type | Description |
|---|---|---|
| `task_id` | `str` | Globally unique slug: `{site_id}__{workflow_slug}` (e.g., `amazon_in__product_search`) |
| `site_id` | `str` | Cross-references `WebsiteProfile.site_id` |
| `website` | `str` | Human-readable site name (e.g., `Amazon India`) |
| `difficulty` | `Literal["simple","medium","complex"]` | Complexity tier (see tier definitions below) |
| `category` | `BenchmarkCategory` | Task category enum (see Part 5) |
| `goal` | `str` | Plain-English statement of what the agent must accomplish. Sent as the `task` field in `/analyze`. Must be specific enough that success is unambiguous. |
| `start_url` | `str` | Exact URL to navigate to before the loop begins |
| `preconditions` | `Preconditions` | Auth and page state requirements (see sub-schema below) |
| `success_criteria` | `list[SuccessCriterion]` | ALL must pass for task to be marked completed |
| `failure_criteria` | `list[FailureCriterion]` | ANY one failing marks the task failed immediately |
| `expected_artifacts` | `list[ArtifactSpec]` | Artifacts the task is expected to produce (optional, for richer reports) |
| `timeout_ms` | `int` | Maximum wall-clock time for the entire task (default: 120,000) |
| `max_steps` | `int` | Maximum loop iterations (default: 25) |
| `retry_budget` | `int` | Maximum step-level retries on validation failure (default: 2) |
| `human_intervention_rules` | `HumanInterventionRules` | When to pause for human vs auto-continue |
| `executor_override` | `Optional[str]` | Force `"playwright"` or `"synthetic"` for this task, ignoring CLI flag |
| `skip_reason` | `Optional[str]` | If set, task is skipped with this message (use for known blockers) |
| `expected_step_range` | `Optional[tuple[int,int]]` | Expected min/max steps for a successful run (informational only, not gating) |

### Preconditions Sub-schema

| Field | Type | Description |
|---|---|---|
| `auth_required` | `bool` | Whether authentication state must be present before the loop starts |
| `auth_strategy` | `str` | `"session_state"` (restore Playwright storage state) or `"credential_login"` (run login sub-flow) or `"none"` |
| `auth_state_file` | `Optional[str]` | Path to `.playwright_state/{site_id}.json` (for `session_state` mode) |
| `page_ready_selector` | `Optional[str]` | CSS selector that must be visible before the loop starts (network-idle is not always enough) |
| `pre_navigation` | `Optional[str]` | URL to visit first (e.g., dismiss cookie consent) before navigating to `start_url` |
| `inject_cookies` | `Optional[list[CookieSpec]]` | Cookies to inject (for locale/currency/consent) |

### SuccessCriterion Schema (extends existing `certification/models.py`)

Existing kinds: `STATE_COMPLETED`, `MIN_COMPLETED_STEPS`, `POST_VALIDATION`, `CONTENT_CONTAINS`, `RECOVERY_USED`, `BOUNDED_FAILURE`, `FAILURE_CATEGORY`, `SEMANTIC_PRESENT`.

New kinds for M0 real-site tasks:

| Kind | Description | `target` field | `value` field |
|---|---|---|---|
| `URL_MATCHES` | Final URL matches regex pattern | regex pattern | — |
| `DOM_ELEMENT_PRESENT` | A CSS selector resolves to ≥1 element on the final page | CSS selector | — |
| `DOM_TEXT_PRESENT` | A specific text string appears anywhere on the final page | text to find | — |
| `DOM_TEXT_ABSENT` | A text string (error message) does NOT appear on the final page | text to avoid | — |
| `EXTRACTED_VALUE_PRESENT` | The AI's extracted output contains a specific key | key name | — |
| `EXTRACTED_VALUE_MATCHES` | The AI's extracted output value matches a pattern | key name | regex in detail |
| `STEP_COUNT_IN_RANGE` | Total steps taken within expected range | — | max_steps (value) |
| `SCREENSHOT_DIFF` | Final screenshot significantly differs from baseline (action had visible effect) | — | min_pixel_diff_pct (value) |

### FailureCriterion Schema (new, M0-specific)

| Field | Type | Description |
|---|---|---|
| `kind` | `FailureCriterionKind` | `DOM_ERROR_PRESENT`, `URL_MATCHES_ERROR`, `HTTP_ERROR`, `RATE_LIMITED` |
| `detail` | `str` | Human description |
| `target` | `Optional[str]` | Text/selector/pattern indicating failure |

Examples:
- `{kind: DOM_ERROR_PRESENT, detail: "Error message appeared", target: "Sorry, something went wrong"}`
- `{kind: URL_MATCHES_ERROR, detail: "Redirected to error page", target: ".*/error.*"}`
- `{kind: HTTP_ERROR, detail: "Got 429 rate limit", target: "429"}`

### HumanInterventionRules Sub-schema

| Field | Type | Description |
|---|---|---|
| `danger_actions` | `str` | One of `"block"` (never execute), `"require_human"` (pause), `"auto_approve"` (only for release validation) |
| `caution_actions` | `str` | One of `"require_human"`, `"auto_approve"` |
| `max_human_interventions` | `int` | If more human interventions are required than this, mark task as HUMAN_REQUIRED (default: 0 for smoke/nightly, 5 for release) |

### ArtifactSpec Sub-schema

| Field | Type | Description |
|---|---|---|
| `artifact_id` | `str` | Identifier for this artifact |
| `type` | `str` | `"extracted_text"`, `"screenshot"`, `"dom_snapshot"`, `"download_file"` |
| `description` | `str` | What this artifact represents |
| `required` | `bool` | Whether the task fails if this artifact is not produced |

### Difficulty Tier Definitions

**Simple:** Single-page tasks with clear, deterministic success. No authentication. The goal can be accomplished in 1–5 steps. A site redesign is unlikely to make this task impossible. The primary failure mode is grounding (wrong selector) or extraction (page not fully rendered).

**Medium:** Multi-step tasks that may span 2–3 pages. Authentication usually required. 5–15 steps. Dynamic content (filters, search results, pagination). The primary failure mode is planning (wrong step sequence) or execution fidelity (React/Vue inputs).

**Complex:** Tasks spanning 5+ pages, possibly multiple tabs, requiring sequential decision-making. Authentication required. 15–30 steps. Success depends on multiple intermediate states being correct. Cross-site tasks are always complex. The primary failure mode is recovery (intermediate state failure) or goal tracking (losing the objective across steps).

---

## Part 4 — The First Benchmark Suite (M0 Task Definitions)

24 tasks plus 3 capability-specific tasks. Organized by difficulty tier.

---

### SIMPLE Tier (tasks 1–8)

---

#### Task 1 — YouTube Search

| Field | Value |
|---|---|
| `task_id` | `youtube_com__video_search` |
| `site_id` | `youtube_com` |
| `website` | `YouTube` |
| `difficulty` | `simple` |
| `category` | `SEARCH` |
| `goal` | `Search for "Python tutorial for beginners" and confirm search results appear` |
| `start_url` | `https://www.youtube.com` |
| `auth_required` | No |
| `timeout_ms` | 60,000 |
| `max_steps` | 8 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Python tutorial" appears in page after search
2. `URL_MATCHES`: URL contains "search_query=Python"
3. `MIN_COMPLETED_STEPS`: At least 2 steps completed (navigate + search)

**Failure Criteria:**
1. `DOM_TEXT_PRESENT`: "Something went wrong" on page

**Expected Artifacts:** Screenshot of search results

**Expected Step Range:** 2–4 steps

**Primary failure modes:** Search box grounding (YouTube has complex nested inputs), query submission (Enter key vs click)

---

#### Task 2 — GitHub Repository Search

| Field | Value |
|---|---|
| `task_id` | `github_com__repo_search` |
| `site_id` | `github_com` |
| `website` | `GitHub` |
| `difficulty` | `simple` |
| `category` | `SEARCH` |
| `goal` | `Search for "fastapi" repositories on GitHub and confirm repositories appear in results` |
| `start_url` | `https://github.com/search?type=repositories` |
| `auth_required` | No |
| `timeout_ms` | 60,000 |
| `max_steps` | 6 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "fastapi" appears in results
2. `URL_MATCHES`: URL contains `q=fastapi`
3. `DOM_ELEMENT_PRESENT`: `[data-testid="results-list"]` or `.search-results`

**Failure Criteria:**
1. `HTTP_ERROR`: 429 (rate limited)
2. `DOM_TEXT_PRESENT`: "We couldn't find any repositories"

**Expected Step Range:** 2–3 steps

---

#### Task 3 — Instagram Profile View (No Auth)

| Field | Value |
|---|---|
| `task_id` | `instagram_com__profile_view` |
| `site_id` | `instagram_com` |
| `website` | `Instagram` |
| `difficulty` | `simple` |
| `category` | `NAVIGATION` |
| `goal` | `Navigate to the Instagram profile for user "nasa" and confirm the profile page loaded` |
| `start_url` | `https://www.instagram.com/nasa/` |
| `auth_required` | No |
| `timeout_ms` | 45,000 |
| `max_steps` | 5 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "nasa" on page
2. `URL_MATCHES`: URL contains `/nasa/`

**Failure Criteria:**
1. `DOM_TEXT_PRESENT`: "Sorry, this page isn't available"
2. `DOM_TEXT_PRESENT`: "Log in to see this content" (login wall triggered)

**Note:** Instagram aggressively prompts for login. Skip task on `DOM_TEXT_PRESENT: "Log in to continue"` — mark as BLOCKED, not FAILED.

**Expected Step Range:** 1–2 steps (navigation only)

---

#### Task 4 — Generic Login Form (Synthetic Fixture — Regression Anchor)

| Field | Value |
|---|---|
| `task_id` | `fixture__login_form` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: Login` |
| `difficulty` | `simple` |
| `category` | `FORM_SUBMIT` |
| `goal` | `Log in with username "tester" and password "secret123", then confirm the welcome message appears` |
| `start_url` | `{fixture_server_base}/login` |
| `auth_required` | No |
| `timeout_ms` | 30,000 |
| `max_steps` | 5 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Welcome tester"
2. `MIN_COMPLETED_STEPS`: 3 (navigate + fill username + fill password + click)

**Why include a fixture task:** This is the regression anchor. If this task fails, the problem is in the loop itself (extraction, analysis, execution), not the website. It is the control condition in every suite.

**Expected Step Range:** 4–5 steps

---

#### Task 5 — Zomato Restaurant Search

| Field | Value |
|---|---|
| `task_id` | `zomato_com__restaurant_search` |
| `site_id` | `zomato_com` |
| `website` | `Zomato` |
| `difficulty` | `simple` |
| `category` | `SEARCH` |
| `goal` | `Search for restaurants serving "biryani" in Bangalore and confirm results appear` |
| `start_url` | `https://www.zomato.com/bangalore` |
| `auth_required` | No |
| `timeout_ms` | 90,000 |
| `max_steps` | 10 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "biryani" in results
2. `DOM_ELEMENT_PRESENT`: Restaurant card elements present

**Failure Criteria:**
1. `DOM_TEXT_PRESENT`: "No restaurants found"
2. `HTTP_ERROR`: 403 (geo-blocked)

**Notes:** Zomato uses geolocation detection. May redirect to a location selector. The agent should handle the location prompt as part of the task. If a CAPTCHA is triggered, mark BLOCKED.

---

#### Task 6 — Generic Pagination (Synthetic Fixture)

| Field | Value |
|---|---|
| `task_id` | `fixture__pagination` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: Pagination` |
| `difficulty` | `simple` |
| `category` | `PAGINATION` |
| `goal` | `Navigate to page 2 of the paged list and confirm page 2 items appear` |
| `start_url` | `{fixture_server_base}/pagination` |
| `auth_required` | No |
| `timeout_ms` | 20,000 |
| `max_steps` | 4 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "page 2"
2. `DOM_TEXT_PRESENT`: "Item C"

---

#### Task 7 — Generic Modal Dialog (Synthetic Fixture)

| Field | Value |
|---|---|
| `task_id` | `fixture__modal_dialog` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: Modal` |
| `difficulty` | `simple` |
| `category` | `DIALOG` |
| `goal` | `Open the settings modal, then save the setting` |
| `start_url` | `{fixture_server_base}/modal` |
| `auth_required` | No |
| `timeout_ms` | 20,000 |
| `max_steps` | 4 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Setting saved"

---

#### Task 8 — Generic File Upload (Synthetic Fixture)

| Field | Value |
|---|---|
| `task_id` | `fixture__file_upload` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: Upload` |
| `difficulty` | `simple` |
| `category` | `UPLOAD` |
| `goal` | `Upload the test file "benchmark_test.txt" using the file input` |
| `start_url` | `{fixture_server_base}/upload` |
| `auth_required` | No |
| `timeout_ms` | 20,000 |
| `max_steps` | 3 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Uploaded: benchmark_test.txt"

**Note:** Tests file input handling. Mode A (Playwright) uses `page.set_input_files()`; Mode B (synthetic) uses the extension's file upload flow. Results should differ here — a Mode A/B gap on this task confirms the file-picker limitation.

---

### MEDIUM Tier (tasks 9–18)

---

#### Task 9 — Amazon Product Search + Price Extraction

| Field | Value |
|---|---|
| `task_id` | `amazon_in__product_search_price` |
| `site_id` | `amazon_in` |
| `website` | `Amazon India` |
| `difficulty` | `medium` |
| `category` | `SEARCH` |
| `goal` | `Search for "wireless headphones" on Amazon India, open the first result, and extract the price` |
| `start_url` | `https://www.amazon.in` |
| `auth_required` | No (browsing) |
| `timeout_ms` | 120,000 |
| `max_steps` | 12 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `URL_MATCHES`: URL contains `/dp/` (product page)
2. `DOM_ELEMENT_PRESENT`: `#priceblock_ourprice` or `[data-a-color="price"]` or `.a-price`
3. `EXTRACTED_VALUE_PRESENT`: AI's response contains a price value (₹ or INR)

**Failure Criteria:**
1. `DOM_TEXT_PRESENT`: "CAPTCHA"
2. `HTTP_ERROR`: 503

**Expected Step Range:** 4–8 steps (search → results → click first result → confirm price visible)

**Notes:** Amazon India uses dynamic class names for prices. This task tests grounding robustness. The LocatorRanker's `text_match` and `aria_label` strategies should outperform raw CSS. Anti-bot detection is likely — record BLOCKED if triggered.

---

#### Task 10 — Flipkart Product Filter

| Field | Value |
|---|---|
| `task_id` | `flipkart_com__product_filter` |
| `site_id` | `flipkart_com` |
| `website` | `Flipkart` |
| `difficulty` | `medium` |
| `category` | `FILTER` |
| `goal` | `Search for "laptop" on Flipkart, apply the "HP" brand filter, and confirm filtered results appear` |
| `start_url` | `https://www.flipkart.com` |
| `auth_required` | No |
| `timeout_ms` | 120,000 |
| `max_steps` | 15 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "HP" in filter state or results
2. `URL_MATCHES`: URL contains filter parameters

**Failure Criteria:**
1. `DOM_TEXT_PRESENT`: "CAPTCHA"
2. `DOM_TEXT_PRESENT`: "No results found"

**Notes:** Flipkart uses aggressively hashed class names. This is a key grounding stress test. Mode A vs Mode B gap expected to be significant here.

---

#### Task 11 — LinkedIn People Search

| Field | Value |
|---|---|
| `task_id` | `linkedin_com__people_search` |
| `site_id` | `linkedin_com` |
| `website` | `LinkedIn` |
| `difficulty` | `medium` |
| `category` | `SEARCH` |
| `goal` | `Search for people with the title "Python Developer" on LinkedIn and confirm results appear` |
| `start_url` | `https://www.linkedin.com/search/results/people/?keywords=Python+Developer` |
| `auth_required` | Yes (session state) |
| `timeout_ms` | 90,000 |
| `max_steps` | 8 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Python Developer" in any result
2. `DOM_ELEMENT_PRESENT`: `.reusable-search__result-container` or similar
3. `MIN_COMPLETED_STEPS`: 2

**Failure Criteria:**
1. `URL_MATCHES_ERROR`: `/login` (auth expired)
2. `DOM_TEXT_PRESENT`: "Join LinkedIn to see who else"

**Auth strategy:** `session_state`, using `.playwright_state/linkedin_com.json` recorded from a test account.

---

#### Task 12 — GitHub: Read PR Comments

| Field | Value |
|---|---|
| `task_id` | `github_com__pr_read_comments` |
| `site_id` | `github_com` |
| `website` | `GitHub` |
| `difficulty` | `medium` |
| `category` | `NAVIGATION` |
| `goal` | `Open pull request #1 in the repository "torvalds/linux" and extract the author's name and the first comment` |
| `start_url` | `https://github.com/torvalds/linux/pull/1` |
| `auth_required` | No |
| `timeout_ms` | 60,000 |
| `max_steps` | 8 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_ELEMENT_PRESENT`: `.comment-body` or similar
2. `EXTRACTED_VALUE_PRESENT`: AI response contains author name
3. `EXTRACTED_VALUE_PRESENT`: AI response contains comment text

**Expected Step Range:** 1–4 steps (likely just navigation + extraction)

**Notes:** Tests DOM extraction quality on a real GitHub PR, which is complex with many interactive elements. A good test of `context_compression`'s ability to surface the relevant parts.

---

#### Task 13 — Google Docs: Create and Type

| Field | Value |
|---|---|
| `task_id` | `docs_google_com__create_type` |
| `site_id` | `docs_google_com` |
| `website` | `Google Docs` |
| `difficulty` | `medium` |
| `category` | `FORM_SUBMIT` |
| `goal` | `Open a new Google Doc, type the text "Hello from the benchmark", and confirm the text appears in the document` |
| `start_url` | `https://docs.new` |
| `auth_required` | Yes (session state) |
| `timeout_ms` | 120,000 |
| `max_steps` | 10 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Hello from the benchmark" (in contenteditable or aria-label with doc content)
2. `URL_MATCHES`: URL contains `docs.google.com/document`

**Failure Criteria:**
1. `URL_MATCHES_ERROR`: `accounts.google.com` (auth expired)

**Notes:** Google Docs uses a canvas-based or contenteditable editor. This is a major grounding and execution stress test. Typing into the doc via synthetic events (Mode B) is expected to fail. Mode A (Playwright's `fill()`) may also struggle with the contenteditable. This task is expected to have low completion in both modes for the first baseline — it specifically tests the limits of the current loop.

**Auth strategy:** `session_state`, using `.playwright_state/google_com.json`.

---

#### Task 14 — Booking.com Hotel Search

| Field | Value |
|---|---|
| `task_id` | `booking_com__hotel_search` |
| `site_id` | `booking_com` |
| `website` | `Booking.com` |
| `difficulty` | `medium` |
| `category` | `SEARCH` |
| `goal` | `Search for hotels in Bangalore for check-in next Saturday, check-out next Sunday, 1 adult, and confirm hotel results appear` |
| `start_url` | `https://www.booking.com` |
| `auth_required` | No |
| `timeout_ms` | 120,000 |
| `max_steps` | 15 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `DOM_ELEMENT_PRESENT`: Hotel result cards
2. `URL_MATCHES`: URL contains `dest_type=city`

**Failure Criteria:**
1. `DOM_TEXT_PRESENT`: "We couldn't find any available properties"
2. `HTTP_ERROR`: 403

**Notes:** Booking.com uses complex date pickers. Tests the AI's ability to interact with date selector widgets. The check-in date is dynamic (next Saturday) — the task definition computes this at run time.

---

#### Task 15 — Generic Multi-step Form (Synthetic Fixture)

| Field | Value |
|---|---|
| `task_id` | `fixture__multistep_form` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: Wizard` |
| `difficulty` | `medium` |
| `category` | `MULTISTEP` |
| `goal` | `Complete the onboarding wizard: enter full name "Test User" in step 1, then enter role "Engineer" in step 2, then click Finish` |
| `start_url` | `{fixture_server_base}/multistep` |
| `auth_required` | No |
| `timeout_ms` | 30,000 |
| `max_steps` | 6 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Onboarding complete"
2. `MIN_COMPLETED_STEPS`: 4

---

#### Task 16 — Canva Design Creation

| Field | Value |
|---|---|
| `task_id` | `canva_com__create_design` |
| `site_id` | `canva_com` |
| `website` | `Canva` |
| `difficulty` | `medium` |
| `category` | `NAVIGATION` |
| `goal` | `Create a new "Presentation" design in Canva and confirm the editor opens` |
| `start_url` | `https://www.canva.com` |
| `auth_required` | Yes (session state) |
| `timeout_ms` | 120,000 |
| `max_steps` | 12 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `URL_MATCHES`: URL contains `/design/`
2. `DOM_ELEMENT_PRESENT`: Canvas editor element (role="main" containing the design area)

**Failure Criteria:**
1. `URL_MATCHES_ERROR`: `canva.com/login` (auth expired)

**Notes:** Canva is a heavy React SPA. This is a stress test for AI reasoning on complex UIs with many interactive elements.

---

#### Task 17 — Infinite Scroll Feed (Synthetic Fixture)

| Field | Value |
|---|---|
| `task_id` | `fixture__infinite_scroll` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: Feed` |
| `difficulty` | `medium` |
| `category` | `INFINITE_SCROLL` |
| `goal` | `Scroll the feed to load more posts until at least 6 posts are visible` |
| `start_url` | `{fixture_server_base}/scroll` |
| `auth_required` | No |
| `timeout_ms` | 30,000 |
| `max_steps` | 8 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "6 posts" or higher in the status element

---

#### Task 18 — MakeMyTrip Flight Search

| Field | Value |
|---|---|
| `task_id` | `makemytrip_com__flight_search` |
| `site_id` | `makemytrip_com` |
| `website` | `MakeMyTrip` |
| `difficulty` | `medium` |
| `category` | `SEARCH` |
| `goal` | `Search for one-way flights from Mumbai (BOM) to Delhi (DEL) for the first day of next month and confirm flight results appear` |
| `start_url` | `https://www.makemytrip.com/flights/` |
| `auth_required` | No |
| `timeout_ms` | 180,000 |
| `max_steps` | 20 |
| `retry_budget` | 3 |

**Success Criteria:**
1. `DOM_ELEMENT_PRESENT`: Flight result cards
2. `URL_MATCHES`: URL contains `from=BOM` and `to=DEL`

**Failure Criteria:**
1. `DOM_TEXT_PRESENT`: "Sorry, no flights found"
2. `HTTP_ERROR`: 429

**Notes:** MakeMyTrip has a complex flight search form with city autocomplete, date picker, and traveler count. Tests multi-field form completion. High grounding challenge. Anti-bot protection likely active.

---

### COMPLEX Tier (tasks 19–24)

---

#### Task 19 — Amazon: Add to Cart Flow

| Field | Value |
|---|---|
| `task_id` | `amazon_in__add_to_cart` |
| `site_id` | `amazon_in` |
| `website` | `Amazon India` |
| `difficulty` | `complex` |
| `category` | `MULTISTEP` |
| `goal` | `Search for "USB-C cable", open the first result that is Prime-eligible, and add it to the cart` |
| `start_url` | `https://www.amazon.in` |
| `auth_required` | No (add to cart works without auth) |
| `timeout_ms` | 180,000 |
| `max_steps` | 20 |
| `retry_budget` | 3 |
| `human_intervention` | `danger_actions: "require_human"` (adding to cart is a purchase-adjacent action — log it but do not block) |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Added to Cart" or "1 item in cart"
2. `URL_MATCHES`: URL is product page or cart confirmation

**Failure Criteria:**
1. `DOM_TEXT_PRESENT`: "CAPTCHA"
2. `DOM_TEXT_PRESENT`: "Currently unavailable"

**Human intervention rules:** `caution_actions: "auto_approve"` (adding to cart is caution, not danger in benchmark mode — note: danger = checkout/purchase).

**Expected Step Range:** 6–15 steps

---

#### Task 20 — Gmail: Read and Summarize (No Send)

| Field | Value |
|---|---|
| `task_id` | `gmail_com__read_summarize` |
| `site_id` | `gmail_com` |
| `website` | `Gmail` |
| `difficulty` | `complex` |
| `category` | `NAVIGATION` |
| `goal` | `Open the most recent email in the inbox and provide a one-sentence summary of its content` |
| `start_url` | `https://mail.google.com/mail/u/0/#inbox` |
| `auth_required` | Yes (session state) |
| `timeout_ms` | 120,000 |
| `max_steps` | 10 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `URL_MATCHES`: URL contains `#inbox/` (email opened)
2. `EXTRACTED_VALUE_PRESENT`: AI response contains summary text

**Failure Criteria:**
1. `URL_MATCHES_ERROR`: `accounts.google.com` (auth expired)
2. `DOM_TEXT_PRESENT`: "Your account has been temporarily disabled"

**Notes:** No sending. This tests the read path only. Tests Gmail's complex SPA with many interactive regions.

**Auth strategy:** `session_state`, using `.playwright_state/google_com.json` (same as Google Docs).

---

#### Task 21 — Generic Table Edit + Confirm (Synthetic Fixture)

| Field | Value |
|---|---|
| `task_id` | `fixture__table_edit` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: CRUD` |
| `difficulty` | `complex` |
| `category` | `TABLE_EDIT` |
| `goal` | `Edit the first row in the customer table and confirm the row is updated` |
| `start_url` | `{fixture_server_base}/crud` |
| `auth_required` | No |
| `timeout_ms` | 30,000 |
| `max_steps` | 6 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Row updated"

---

#### Task 22 — Cross-Site: Amazon Search → Open in GitHub

This task intentionally tests multi-tab or sequential cross-site reasoning.

| Field | Value |
|---|---|
| `task_id` | `cross_site__amazon_search_github_compare` |
| `site_id` | `cross_site` |
| `website` | `Cross-Site (Amazon→GitHub)` |
| `difficulty` | `complex` |
| `category` | `CROSS_SITE` |
| `goal` | `On Amazon, search for a "Raspberry Pi 4" product. Then, on GitHub, search for the "raspberrypi/linux" repository. Confirm both searches succeeded and report the Amazon price and GitHub star count.` |
| `start_url` | `https://www.amazon.in` |
| `auth_required` | No |
| `timeout_ms` | 240,000 |
| `max_steps` | 25 |
| `retry_budget` | 3 |

**Success Criteria:**
1. `EXTRACTED_VALUE_PRESENT`: Amazon price in AI response
2. `EXTRACTED_VALUE_PRESENT`: GitHub star count in AI response

**Failure Criteria:**
1. `DOM_TEXT_PRESENT`: "CAPTCHA" on either site

**Notes:** This task is expected to be a hard baseline failure in M0. The current system has no multi-tab coordination (the `tabs` subsystem is orphaned). The task will likely fail because the agent will be confused when it opens the second site. That is EXPECTED — it tells us exactly what M4 needs to fix. Record it as PLANNING_FAILURE if the agent gets confused, or ORCHESTRATION_FAILURE if it fails to open the second site at all.

---

#### Task 23 — Google Sheets: Enter Data in Cell

| Field | Value |
|---|---|
| `task_id` | `sheets_google_com__enter_data` |
| `site_id` | `sheets_google_com` |
| `website` | `Google Sheets` |
| `difficulty` | `complex` |
| `category` | `FORM_SUBMIT` |
| `goal` | `Open a new Google Sheet, click on cell A1, type the number 42, press Enter, and confirm the value is in cell A1` |
| `start_url` | `https://sheets.new` |
| `auth_required` | Yes (session state) |
| `timeout_ms` | 150,000 |
| `max_steps` | 12 |
| `retry_budget` | 3 |

**Success Criteria:**
1. `URL_MATCHES`: URL contains `spreadsheets`
2. `DOM_TEXT_PRESENT`: "42" (or confirmed by extraction)

**Notes:** Google Sheets uses a canvas-based cell grid. Clicking a specific cell requires coordinate-based interaction — the accessibility tree may not expose individual cells. This is expected to be a hard baseline failure and specifically tests the limits of text-only grounding vs coordinate/visual grounding (M3 territory).

---

#### Task 24 — Government Portal: Generic Form

| Field | Value |
|---|---|
| `task_id` | `generic_gov__form_fill` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: Government-style Form` |
| `difficulty` | `complex` |
| `category` | `FORM_SUBMIT` |
| `goal` | `Complete the multi-step registration form: enter name "Test User", select country "India", accept terms, then submit and confirm the success message` |
| `start_url` | `{fixture_server_base}/register` |
| `auth_required` | No |
| `timeout_ms` | 45,000 |
| `max_steps` | 8 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Account created"

**Notes:** Uses the existing registration fixture. Tests multi-field form completion with select dropdown and checkbox — patterns common on government portals.

---

### Capability-Specific Tasks (3 additional)

These tasks specifically measure individual system capabilities.

---

#### Task 25 — File Download Detection (Synthetic Fixture)

| Field | Value |
|---|---|
| `task_id` | `fixture__file_download` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: Download` |
| `difficulty` | `simple` |
| `category` | `DOWNLOAD` |
| `goal` | `Click the download link to download the report file` |
| `start_url` | `{fixture_server_base}/download` |
| `auth_required` | No |
| `timeout_ms` | 20,000 |
| `max_steps` | 3 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_ELEMENT_PRESENT`: `#dl` link present
2. `MIN_COMPLETED_STEPS`: 2 (navigate + click)

**Artifacts:** Captured download file (if Playwright captures it).

---

#### Task 26 — Dynamic Content Loading (Synthetic Fixture)

| Field | Value |
|---|---|
| `task_id` | `fixture__dynamic_load` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: Dynamic` |
| `difficulty` | `simple` |
| `category` | `DYNAMIC_LOADING` |
| `goal` | `Wait for the "Ready" button to appear (it loads after a delay) and click it` |
| `start_url` | `{fixture_server_base}/dynamic` |
| `auth_required` | No |
| `timeout_ms` | 20,000 |
| `max_steps` | 5 |
| `retry_budget` | 2 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "Loaded"

**Notes:** Tests the agent's ability to wait for dynamic content and retry when elements are not yet present. Specifically tests the loop's wait/retry behavior.

---

#### Task 27 — Accordion Interaction (Synthetic Fixture)

| Field | Value |
|---|---|
| `task_id` | `fixture__accordion` |
| `site_id` | `fixture_server` |
| `website` | `Fixture: FAQ Accordion` |
| `difficulty` | `simple` |
| `category` | `ACCORDION` |
| `goal` | `Expand the second FAQ question ("How much?") and confirm its answer is visible` |
| `start_url` | `{fixture_server_base}/accordion` |
| `auth_required` | No |
| `timeout_ms` | 15,000 |
| `max_steps` | 3 |
| `retry_budget` | 1 |

**Success Criteria:**
1. `DOM_TEXT_PRESENT`: "q2 expanded"

---

## Part 5 — Metrics Design

### Primary Metrics (the number that gates M1)

These five metrics define whether the agent can complete real tasks.

---

#### P1 — Task Completion Rate (the primary metric)

**Definition:** Percentage of tasks that reached a `COMPLETED` status.

**Formula:** `completed_tasks / total_tasks_attempted`

**Segmented by:**
- Overall (all 27 tasks)
- By difficulty tier: simple | medium | complex
- By executor mode: playwright | synthetic
- By site: per site
- By category: per benchmark category

**Why segmented:** A 70% overall rate is meaningless without knowing "70% of simple tasks and 10% of complex" vs "45% of all tiers."

**Reported as:** Percentage with 95% confidence interval over multiple runs. Single-run confidence interval: use Wilson score interval with n = tasks_in_tier.

---

#### P2 — Step Success Rate

**Definition:** Percentage of individual steps (loop iterations) that produced a successful execution AND a passing step-level validation.

**Formula:** `steps_with_passing_validation / total_steps_executed`

**Why:** A task might fail on step 8 of 10 despite steps 1–7 succeeding. This metric tracks per-step quality and reveals which action types fail most often.

**Segmented by:** action type (click, type, navigate, extract, scroll, wait)

---

#### P3 — Human Intervention Rate

**Definition:** Percentage of steps that required a human approval (danger/caution actions that exceeded `max_human_interventions`).

**Formula:** `steps_requiring_human / total_steps_executed`

**Why:** In smoke/nightly mode, danger actions cause a BLOCKED result rather than a human pause. This metric reveals how often the agent proposes dangerous actions, even in benchmark mode. A high rate indicates the trust classifier needs calibration.

---

#### P4 — Recovery Success Rate

**Definition:** Percentage of step-level recovery attempts that led to eventual step success.

**Formula:** `recoveries_leading_to_success / total_recovery_attempts`

**Why:** This measures the loop's ability to self-heal without human intervention. Currently 0 in the live loop (no recovery wired in). M2 should move this above 50%.

---

#### P5 — Validation Pass Rate

**Definition:** Percentage of step-level validations that passed.

**Formula:** `step_validations_passed / step_validations_attempted`

**Why:** Distinct from P2 (step success rate). A step can execute without error but still fail validation (e.g., the click happened but the expected text didn't appear). Validation pass rate measures whether the loop correctly identifies outcome success/failure.

---

### Secondary Metrics (diagnostic, not gating)

These metrics diagnose WHERE time and cost go. They inform optimization but do not gate M1.

| Metric | Description | Unit |
|---|---|---|
| `avg_observe_time_ms` | Average time to extract DOM snapshot per step | ms |
| `avg_analyze_time_ms` | Average time for `/analyze` (Gemini call) to return | ms |
| `avg_execute_time_ms` | Average time for action execution per step | ms |
| `avg_validate_time_ms` | Average time for step validation per step | ms |
| `avg_recover_time_ms` | Average time for recovery attempt per step | ms |
| `p95_task_duration_ms` | 95th percentile of total task duration | ms |
| `avg_steps_per_task` | Average steps taken per task (by tier) | count |
| `avg_ai_calls_per_task` | Average `/analyze` calls per completed task | count |
| `avg_tokens_per_task` | Average total tokens (prompt + completion) per task | count |
| `estimated_cost_per_task_usd` | Estimated Gemini API cost per task | USD |
| `estimated_cost_per_run_usd` | Total Gemini API cost for a full suite run | USD |
| `locator_strategy_distribution` | Which locator strategies succeeded (count per strategy) | dict |
| `captcha_blocked_rate` | Percentage of tasks blocked by CAPTCHA | % |
| `screenshot_count_per_task` | Average screenshots taken per task | count |

---

### Metric Computation Rules

1. **Count only attempted tasks.** A SKIPPED task does not count in the denominator.
2. **BLOCKED ≠ FAILED.** Blocked tasks (CAPTCHA, rate limit) are reported separately and excluded from the completion rate denominator. A CAPTCHA block is not a reasoning failure.
3. **Confidence intervals.** All rates are reported with Wilson score 95% confidence intervals. Intervals wider than ±10% indicate insufficient runs — recommend repeating.
4. **Baseline comparison.** After M0's first full run, `baseline.json` is written and locked. Subsequent runs report delta from baseline: `(current_rate - baseline_rate)`. Negative deltas are regressions.
5. **Per-executor comparison.** When both modes are run, the document reports a "execution gap" per tier: `playwright_completion - synthetic_completion`. This gap quantifies how much M1 will gain.

---

## Part 6 — Failure Taxonomy

Every failure is assigned exactly one category. The classifier uses a decision tree evaluated at the point of failure.

### Taxonomy Categories

| Category | Description | Example |
|---|---|---|
| `GROUNDING` | The AI identified the correct action but the element could not be located on the page. The locator failed all strategies. | AI says "click the Submit button" but no element with role=button and name=Submit is found |
| `PLANNING` | The AI suggested an action that is logically incorrect or out of sequence. The right element was found but the action sent the task in the wrong direction. | AI clicks "Cancel" when it should click "Confirm" |
| `EXECUTION` | The element was found and the action was invoked, but the page did not respond (untrusted events rejected, React controlled input ignored, DOM mutation did not occur). | `element.click()` ran but the form did not submit |
| `VALIDATION` | The action executed, a DOM mutation occurred, but the expected post-condition was not met. | The button was clicked, the page loaded, but the expected "Success" text is not present |
| `RECOVERY` | Step failed, recovery was attempted, recovery also failed. The task is lost after retries. | Step 5 failed grounding, retry with alternate locator also failed, task aborted |
| `TIMEOUT` | The task exceeded its `timeout_ms` or `max_steps` budget without completing. | A 25-step task did not complete in 120 seconds |
| `BLOCKED_CAPTCHA` | The site presented a CAPTCHA challenge that the agent cannot solve. | Cloudflare challenge page detected |
| `BLOCKED_RATE_LIMIT` | The site returned HTTP 429 or equivalent rate-limit response. | Too many requests in rapid succession |
| `BLOCKED_AUTH_EXPIRED` | Saved authentication state was invalid (session expired, redirect to login). | Playwright storage state did not restore a valid session |
| `BLOCKED_LOGIN_WALL` | The site requires authentication but auth was not configured for this task. | Site shows "Log in to continue" for an unauthenticated task |
| `BLOCKED_ANTI_BOT` | The site detected automation and blocked or fingerprinted the session. | Datadome or Akamai bot detection triggered |
| `PERCEPTION` | The agent's DOM extraction was incomplete or malformed — elements that are visually present were not in the extracted snapshot. | A button in a shadow DOM was invisible to the extractor |
| `ORCHESTRATION` | Failure to coordinate across steps, pages, or tasks (applies to cross-site and multi-tab tasks). | Agent lost track of the goal when navigating from site 1 to site 2 |
| `VISION_REQUIRED` | The task requires visual/coordinate interaction but the agent has no screenshot-based grounding (canvas, custom widget, drag-drop). | Google Sheets cell selection requires coordinate click |
| `INFRASTRUCTURE` | Runner-level error unrelated to agent behavior (Playwright crashed, backend down, network error). | `playwright.TimeoutError` from network issue |
| `UNKNOWN` | Failure does not clearly match any category above. These are investigated manually. | Catch-all for novel failures |

### Classification Decision Tree

At the moment a step fails, apply this decision tree to assign the category:

```
Is the failure an infrastructure error (Playwright crash, HTTP 5xx, network)?
  YES → INFRASTRUCTURE

Is a CAPTCHA detected on the page?
  YES → BLOCKED_CAPTCHA

Did we get HTTP 429 or rate-limit response?
  YES → BLOCKED_RATE_LIMIT

Was the user redirected to a login page?
  YES → BLOCKED_AUTH_EXPIRED or BLOCKED_LOGIN_WALL

Was automation detection triggered (Datadome/Cloudflare JS challenge)?
  YES → BLOCKED_ANTI_BOT

Did the locator resolution fail ALL strategies (element not found)?
  YES → GROUNDING

Did the locator resolution succeed but the action call threw an error?
  AND is the element visually present in the screenshot but not in the DOM extraction?
    YES → PERCEPTION
  AND is the element present but unresponsive to interaction?
    YES → EXECUTION

Did the action execute without error but the expected DOM change did not occur?
  YES → EXECUTION

Did the DOM change occur but the success criterion was not met?
  YES → VALIDATION

Was recovery attempted and did recovery also fail?
  YES → RECOVERY

Did the task run out of time or steps?
  YES → TIMEOUT

Did the agent take an action that was clearly wrong in sequence (navigated to wrong page, clicked wrong element type)?
  YES → PLANNING

Did a cross-site or multi-tab coordination fail?
  YES → ORCHESTRATION

Did the task require a visual click that has no DOM equivalent?
  YES → VISION_REQUIRED

None of the above → UNKNOWN
```

### Failure Escalation

- UNKNOWN failures must be triaged within 24 hours on nightly runs.
- INFRASTRUCTURE failures are retried once automatically (in case of transient network error).
- BLOCKED_* failures are not retried (the block will persist).
- GROUNDING failures feed back to the LocatorRanker strategy tuning backlog.
- EXECUTION failures are tagged for M1 investigation (the CDP driver gap).
- PLANNING failures are fed back to prompt engineering and context_compression tuning.

---

## Part 7 — Report Design

Three report formats: JSON (machine-readable), Markdown (human-readable audit), HTML (visual dashboard).

### JSON Report (`m0-{run_id}.json`)

The JSON report is the canonical artifact. All other formats are derived from it.

**Top-level structure:**

```json
{
  "meta": {
    "run_id": "m0-20260629-001",
    "suite": "nightly",
    "executor_mode": "playwright",
    "backend_url": "http://localhost:8000",
    "started_at": "2026-06-29T22:00:00Z",
    "completed_at": "2026-06-29T22:45:12Z",
    "duration_s": 2712,
    "baseline_run_id": "m0-20260629-000",
    "is_first_run": false
  },
  "summary": {
    "tasks_attempted": 24,
    "tasks_completed": 11,
    "tasks_failed": 8,
    "tasks_blocked": 3,
    "tasks_skipped": 2,
    "tasks_error": 0,
    "completion_rate": 0.458,
    "completion_rate_ci_95": [0.267, 0.661],
    "completion_rate_delta_from_baseline": -0.021,
    "step_success_rate": 0.623,
    "human_intervention_rate": 0.08,
    "recovery_success_rate": 0.0,
    "validation_pass_rate": 0.71,
    "estimated_cost_usd": 1.24,
    "regression_warnings": []
  },
  "by_difficulty": {
    "simple": {"attempted": 10, "completed": 8, "completion_rate": 0.8},
    "medium": {"attempted": 10, "completed": 3, "completion_rate": 0.3},
    "complex": {"attempted": 4, "completed": 0, "completion_rate": 0.0}
  },
  "by_category": { ... },
  "by_site": { ... },
  "failure_distribution": {
    "GROUNDING": 4,
    "PLANNING": 2,
    "EXECUTION": 5,
    "VALIDATION": 1,
    "BLOCKED_CAPTCHA": 2,
    "BLOCKED_AUTH_EXPIRED": 1,
    "TIMEOUT": 1,
    "VISION_REQUIRED": 2,
    "ORCHESTRATION": 1,
    "UNKNOWN": 0
  },
  "locator_strategies": {
    "accessibility_name": 82,
    "aria_label": 14,
    "data_testid": 31,
    "text_match": 28,
    "css_selector": 67,
    "xpath": 5,
    "all_failed": 12
  },
  "task_results": [
    {
      "task_id": "youtube_com__video_search",
      "website": "YouTube",
      "difficulty": "simple",
      "category": "SEARCH",
      "status": "COMPLETED",
      "steps_taken": 3,
      "steps_successful": 3,
      "steps_failed": 0,
      "human_interventions": 0,
      "recoveries_attempted": 0,
      "validations_passed": 3,
      "validations_failed": 0,
      "ai_calls": 3,
      "total_tokens": 4821,
      "estimated_cost_usd": 0.048,
      "observe_time_ms": 450,
      "analyze_time_ms": 1820,
      "execute_time_ms": 280,
      "total_duration_ms": 8200,
      "failure_layer": null,
      "failure_detail": null,
      "criteria_results": [
        {"kind": "DOM_TEXT_PRESENT", "detail": "Python tutorial in results", "passed": true, "observed": "found"},
        {"kind": "URL_MATCHES", "detail": "search_query in URL", "passed": true, "observed": "url=youtube.com/results?search_query=..."}
      ],
      "screenshots": [
        "screenshots/m0-20260629-001/youtube_com__video_search/step_001_baseline.png",
        "screenshots/m0-20260629-001/youtube_com__video_search/step_002_post_action.png",
        "screenshots/m0-20260629-001/youtube_com__video_search/step_003_final.png"
      ],
      "timeline": "timelines/m0-20260629-001/youtube_com__video_search.json"
    }
  ],
  "reliability": { ... },
  "failure_catalog": { ... },
  "recommendations": [ ... ]
}
```

---

### Markdown Report (`m0-{run_id}.md`)

Human-readable. Committed to the repository on release runs.

```markdown
# M0 Benchmark Report — 2026-06-29 (Run #001)

**Suite:** nightly | **Executor:** playwright | **Duration:** 45m 12s

## Summary

| Metric | Value | Delta from Baseline |
|---|---|---|
| Task Completion Rate | **45.8%** | -2.1% ⚠️ |
| Simple Tier | 80.0% | +0.0% |
| Medium Tier | 30.0% | -3.0% |
| Complex Tier | 0.0% | 0.0% |
| Step Success Rate | 62.3% | — |
| Recovery Success Rate | 0.0% | — |
| Estimated Cost | $1.24 | — |

## Completed Tasks ✅

- [PASS] YouTube Video Search (simple/SEARCH) — 3 steps, $0.05
- [PASS] GitHub Repository Search (simple/SEARCH) — 2 steps, $0.03
- [PASS] Fixture: Login Form (simple/FORM_SUBMIT) — 4 steps, $0.02
- ... (all completed tasks)

## Failed Tasks ❌

- [FAIL] Amazon Product Filter (medium/FILTER) — GROUNDING: No element found for "HP brand filter" after 6 strategies
- [FAIL] Google Docs Create+Type (medium/FORM_SUBMIT) — EXECUTION: contenteditable fill rejected by React controlled input
- ... (all failed tasks)

## Blocked Tasks 🚫

- [BLOCKED] Instagram Profile View (simple/NAVIGATION) — BLOCKED_LOGIN_WALL: "Log in to see this content"
- ... (all blocked tasks)

## Failure Distribution

| Category | Count | % of Failures |
|---|---|---|
| EXECUTION | 5 | 38.5% |
| GROUNDING | 4 | 30.8% |
| VISION_REQUIRED | 2 | 15.4% |
| BLOCKED_CAPTCHA | 2 | 15.4% |
| PLANNING | 2 | 15.4% |

## Locator Strategy Success

| Strategy | Successes | % of Resolutions |
|---|---|---|
| accessibility_name | 82 | 36.3% |
| css_selector | 67 | 29.6% |
| data_testid | 31 | 13.7% |
| text_match | 28 | 12.4% |
| aria_label | 14 | 6.2% |
| xpath | 5 | 2.2% |
| all_failed | 12 | — |

## Recommendations

- EXECUTION failures (38.5%) dominate — M1 (CDP trusted driver) is the highest-leverage fix.
- GROUNDING failures include 4 cases where all 6 strategies failed — investigate screenshots for these tasks.
- VISION_REQUIRED failures confirm Google Sheets/Docs canvas tasks require M3 (visual grounding).
- Recovery success rate is 0.0% — M2 (closed loop with recovery) is unblocked.
```

---

### HTML Report (`m0-{run_id}.html`)

Self-contained HTML file with inline CSS/JS. No external dependencies. Viewable offline.

**Structure:**
1. **Header bar**: Run ID, suite, executor mode, date, overall completion rate (large, color-coded: red <40%, yellow 40–70%, green >70%).
2. **Summary cards**: Five primary metrics as cards with baseline delta arrows.
3. **Tier breakdown table**: simple/medium/complex completion rates with bar chart.
4. **Failure distribution donut chart**: Category → count.
5. **Task table**: Expandable rows. One row per task. Columns: status (icon), task name, site, difficulty, steps, cost, failure layer. Expanded row shows: criteria results, step timeline, screenshots (thumbnails), failure detail.
6. **Locator strategy chart**: Bar chart of strategy success counts.
7. **Timeline view**: Interactive timeline of steps for a selected task.
8. **Baseline comparison**: If `baseline.json` exists, side-by-side comparison of current vs baseline for all metrics.

The HTML report is the primary artifact for humans. Screenshots are embedded as base64 thumbnails (full screenshots are linked as external files). The report is self-contained and can be shared without a web server.

---

## Part 8 — CI Integration

### Three Benchmark Tiers

#### Smoke Benchmark (runs on every PR)

**Trigger:** Every pull request that modifies `backend/app/` or `extension/src/`.  
**Suite:** 5 tasks (fixture__login_form, fixture__pagination, fixture__modal, youtube_com__video_search, github_com__repo_search)  
**Executor:** `playwright`  
**Mode:** Headless  
**Timeout:** 10 minutes  
**Human approval:** None (all blocked/auto-approved)  
**Backend:** CI spins up the backend against a SQLite test DB  
**Real AI:** Yes (uses `GEMINI_API_KEY` from CI secrets)  
**Cost:** ~$0.20 per run  
**Pass criteria:**  
- Fixture tasks must COMPLETE (smoke failures = broken loop)  
- Real-site tasks may be BLOCKED (anti-bot) but must not ERROR  
- No regression of >10% from smoke baseline  
**Output:** JSON summary appended to PR comment  
**On failure:** Block merge unless labeled `[skip-benchmark]`  

#### Nightly Benchmark (runs once per day)

**Trigger:** Cron: 2:00 AM UTC, Monday–Friday  
**Suite:** All 27 tasks  
**Executor:** Both `playwright` AND `synthetic` (two parallel runs)  
**Mode:** Headless  
**Timeout:** 90 minutes  
**Human approval:** None  
**Cost:** ~$2.50 per run (both modes)  
**Pass criteria:**  
- Completion rate must not drop >5% from the M0 baseline  
- Simple tier completion rate must be ≥ 60% (alert if below)  
- INFRASTRUCTURE failures must be 0 (investigate immediately)  
**Output:** HTML report committed to `reports/nightly/m0-{date}.html`  
**On regression:** File a GitHub issue with the report attached; alert to the team Slack channel  

#### Release Benchmark (runs before every release)

**Trigger:** Manual trigger by release owner. Required before any version tag is created.  
**Suite:** All 27 tasks  
**Executor:** `playwright` (primary), `synthetic` (secondary run)  
**Mode:** Headed (human can observe)  
**Human approval:** Enabled for danger/caution actions (max 3 human interventions per task)  
**Timeout:** No limit (human present)  
**Pass criteria:**  
- Must satisfy M1 success gates before tagging M1 release (see Part 9)  
**Output:** HTML report committed to `reports/release/` with a human sign-off checklist  
**Sign-off required from:** The engineer running the release AND one reviewer  

---

### CI Pipeline Specification (Pseudocode)

```
on: [pull_request]
jobs:
  smoke-benchmark:
    steps:
      1. checkout
      2. pip install -r requirements.txt -r requirements-benchmark.txt
      3. npm run build:extractor  # compile extractor_v2.ts to JS for injection
      4. python -m backend.app (background, port 8000, SQLite)
      5. python -m benchmark.m0_runner \
           --suite smoke \
           --executor playwright \
           --backend http://localhost:8000 \
           --output reports/ci-smoke-{PR_NUMBER}.json \
           --headless
      6. python -m benchmark.ci_check \
           --report reports/ci-smoke-{PR_NUMBER}.json \
           --baseline benchmark/baselines/smoke.json \
           --regression-threshold 0.10  # fail CI if >10% regression
      7. post PR comment with JSON summary
```

---

### Requirements File Separation

The benchmark requires Playwright and additional dependencies that should NOT be in production `requirements.txt`:

**New file: `requirements-benchmark.txt`:**
```
playwright>=1.45.0
pytest-playwright>=0.5.0
pyyaml>=6.0
jinja2>=3.1  # for HTML report templating
requests>=2.32  # for calling /analyze
```

**Production `requirements.txt`** remains unchanged. The benchmark is a dev/CI tool, not a production dependency.

**Playwright installation step** (added to CI pipeline, not to requirements):
```
playwright install chromium
```

---

## Part 9 — Success Gates

M1 cannot begin until all M0 gates are satisfied. Every gate is objectively measurable.

### M0 Completion Gate (unlocks M0 → M1 transition)

The following must ALL be true for M0 to be considered complete and M1 to begin:

| Gate | Requirement | Measurement |
|---|---|---|
| G0.1 — Baseline published | `benchmark/baselines/nightly.json` exists and was produced by a full 27-task nightly run | File exists, `meta.tasks_attempted == 27` |
| G0.2 — Smoke suite stable | Smoke benchmark passes on 5 consecutive CI runs (no fixture task failures, no INFRASTRUCTURE errors) | CI run history |
| G0.3 — Simple tier measured | Simple tier completion rate is recorded (any value, even 0%) | `by_difficulty.simple.completion_rate` is present in baseline |
| G0.4 — Failure catalog populated | At least 10 distinct failure records in the failure catalog from a nightly run | `failure_catalog.total_distinct >= 10` |
| G0.5 — Cost per run measured | Estimated cost per full nightly run is recorded | `meta.estimated_cost_usd > 0` |
| G0.6 — Executor gap measured | Both `playwright` and `synthetic` modes have been run on the same 27-task suite | Two entries in `by_executor` in the baseline |
| G0.7 — Nightly CI established | Nightly cron job is configured and has produced at least 3 consecutive reports | Report files in `reports/nightly/` |
| G0.8 — Team sign-off | The first release benchmark report has been reviewed and signed off by the lead engineer | Sign-off checklist in release report |

### Expected M0 Baseline (pre-implementation estimates — to be replaced by measured values)

These are estimates based on the architectural analysis. They are NOT gates. They are the expectation that will either be confirmed or corrected by M0:

| Tier | Expected Playwright Completion | Expected Synthetic Completion |
|---|---|---|
| Simple | 60–80% | 40–60% |
| Medium | 20–40% | 10–25% |
| Complex | 5–15% | 0–10% |
| **Overall** | **35–55%** | **20–40%** |

If measured values are significantly different from these estimates (>20% in either direction), investigate before proceeding to M1. A much higher-than-expected rate means the tasks are too easy. A much lower rate may indicate a harness bug rather than agent limitation.

### M1 Success Gate (what M1 must achieve to be merged)

These gates define the measurable improvement M1 must produce. They are set NOW (before implementation) so that M1 cannot be merged without meeting them.

| Gate | Requirement | Why |
|---|---|---|
| G1.1 — Execution gap narrows | `(playwright_rate - synthetic_rate) for simple tier` decreases by ≥30% compared to M0 baseline | M1's CDP driver should close the execution fidelity gap |
| G1.2 — Simple tier improves | Simple tier completion rate (synthetic mode) increases by ≥20 percentage points vs M0 baseline | The most direct proof that the trusted driver works |
| G1.3 — EXECUTION failures decrease | EXECUTION failure category share drops from M0 baseline by ≥40% | M1 specifically addresses execution failures |
| G1.4 — No simple tier regression | Simple tier completion does not go DOWN | M1 should not break what works |
| G1.5 — Smoke suite still passes | Smoke benchmark continues to pass on the M1 branch | Regression gate |
| G1.6 — Shadow/iframe coverage | At least 2 new tasks that previously failed GROUNDING now pass due to shadow/iframe traversal | Specific M1 capability |

### M2 Success Gate (what M2 must achieve)

| Gate | Requirement |
|---|---|
| G2.1 — Recovery rate > 0 | `recovery_success_rate > 0.30` (recovery sometimes works) |
| G2.2 — Medium tier improves | Medium tier completion (playwright mode) increases ≥15pp vs M1 baseline |
| G2.3 — Loop-closure evidence | At least 3 tasks that previously TIMED_OUT now complete (the agent recovered from a wrong step) |

---

## Part 10 — Risk Analysis

### Risk Matrix

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| **CAPTCHA on target sites** | HIGH (Amazon, Flipkart, Instagram, Zomato) | HIGH (task blocked, no data) | Add to `BLOCKED_CAPTCHA` taxonomy; do not count as failures. Use `recording_mode: recorded` for CAPTCHA-heavy sites in nightly. Accept that baseline for these sites may be 0%. Re-test with different IP/user-agent. |
| **Login expiry (session state)** | MEDIUM (Google, LinkedIn — sessions last 7–30 days) | MEDIUM (auth-dependent tasks fail) | Refresh Playwright storage states weekly via a script (manual step). Alert when `BLOCKED_AUTH_EXPIRED` appears in nightly. Rotate test accounts. |
| **Site DOM changes** | MEDIUM (Flipkart, Canva — weekly deploys) | MEDIUM-HIGH (grounding fails on stale selectors) | Grounding uses semantic strategies (role+name, text) not CSS classes — should be resilient to CSS changes. Record failure as GROUNDING; investigate after 3+ occurrences. |
| **Rate limiting** | MEDIUM (Amazon, MakeMyTrip) | MEDIUM (task blocked) | Enforce `WebsiteProfile.rate_limit_delay_ms`. Add jitter between tasks. Treat 429 as BLOCKED_RATE_LIMIT, not failure. Use recorded sessions for nightly to reduce live traffic. |
| **Anti-bot detection** | HIGH (Flipkart/Amazon in headless mode) | HIGH (all tasks on that site blocked) | Use `playwright` in non-headless mode for development. Add realistic user-agent and viewport. Accept headless blocking as BLOCKED_ANTI_BOT. For nightly CI, use pre-recorded sessions for affected sites. |
| **Network instability in CI** | LOW | HIGH (flaky benchmark results) | All tasks have `retry_budget` for network-related failures. Tag `INFRASTRUCTURE` failures for re-run rather than recording as task failures. Retry CI workflow once on infrastructure failures. |
| **Gemini API rate limits** | LOW | HIGH (all `/analyze` calls fail) | Backend already handles rate limit errors with HTTP 503/429 → map to INFRASTRUCTURE failure. Add 1s delay between `/analyze` calls in benchmark runner. |
| **Playwright browser crash** | LOW | LOW per task (isolated) | Each task runs in its own browser context. Crash = INFRASTRUCTURE failure for that task only. Runner catches exception and continues. |
| **Benchmark harness bugs** | MEDIUM (first implementation) | HIGH (wrong baseline) | Add a harness self-test that runs the 10 synthetic fixture tasks and asserts ≥90% completion (these should always pass). Harness self-test must pass before any real-site data is collected. |
| **Flaky test ordering (task A affects task B)** | LOW | MEDIUM | Tasks for the same site share auth state but have isolated browser contexts. Tasks for different sites are fully isolated. The fixture server is independent of real sites. |
| **Test credentials compromised** | LOW | HIGH | Credentials stored in `.benchmark_secrets` (gitignored). Use test accounts with no real personal data or payment information. Rotate credentials immediately on any suspected exposure. |
| **Google Docs/Sheets canvas** | CERTAINTY (these tasks will fail) | LOW (known baseline failure) | These tasks are included to document the VISION_REQUIRED failure mode, not to pass. Their failure is expected and meaningful — it justifies M3. |
| **Cross-site task expected to fail** | CERTAINTY (task 22 will fail) | LOW (known baseline failure) | This task documents the ORCHESTRATION gap that M4 addresses. Its failure is informative. |
| **Benchmark cost overruns** | LOW | MEDIUM | Cost is bounded by `max_steps × tasks_count × cost_per_analyze_call`. For 27 tasks × 25 steps × $0.002/call = ~$1.35/run. Monitor and alert if > $5/run (indicates a loop that's not terminating). |
| **Dynamic dates in travel tasks** | MEDIUM (MakeMyTrip, Booking) | LOW | Tasks use dynamic date computation ("first day of next month"). If the site presents a complex calendar interaction, the agent may fail to navigate it — record as PLANNING or GROUNDING. The dynamic date is a feature, not a bug — static dates break after one week. |
| **Ghost recordings (auth state from wrong environment)** | LOW | MEDIUM | Auth state files are named by `site_id`. Guard against accidentally using a production account — benchmark secrets should use dedicated test accounts. Document this clearly in the onboarding guide. |
| **Concurrent benchmark runs** | LOW | MEDIUM | Two concurrent runs to the same backend could interfere via shared session IDs. Benchmark runner generates unique `benchmark_{task_id}_{run_id}` session IDs. The backend's in-memory state is session-scoped. Avoid concurrent nightly runs. |

---

### Risk for the Benchmark Itself (meta-risks)

These risks would make the benchmark produce wrong answers, not just fail tasks.

| Meta-risk | Description | Mitigation |
|---|---|---|
| **Overfit to easy tasks** | If we select only tasks that the current agent can pass, the baseline looks better than reality. | The suite includes 4 complex tasks expected to FAIL. Never remove failing tasks from the suite; they are the signal. |
| **Mode confusion** | Reporting playwright results as if they are synthetic (production) results would create a falsely optimistic baseline. | Every report clearly labels executor mode. Baseline JSON includes `executor_mode` in meta. |
| **Silent CAPTCHA pass** | If CAPTCHA detection fails, a CAPTCHA task could be recorded as a PLANNING failure (wrong task direction) rather than BLOCKED. | Add explicit CAPTCHA detection checks at the top of each loop iteration. Any page with "CAPTCHA", "I'm not a robot", "security check" in DOM is immediately classified. |
| **One-run baseline** | A single nightly run may capture a flaky state (site down, CDN issue). | Run the nightly suite 3 times on the first week. Publish baseline only after seeing ≤5% variance across runs. |

---

## Appendix A: Credential and Auth State Management

### Storing Credentials

Credentials for benchmark test accounts are stored in `.benchmark_secrets` at the repository root. This file is gitignored and must never be committed.

Format:
```json
{
  "google_com": {
    "email": "benchmark-test@example.com",
    "password": "...",
    "recovery_email": "..."
  },
  "linkedin_com": {
    "email": "...",
    "password": "..."
  }
}
```

Each key matches a `WebsiteProfile.credentials_key`. The benchmark runner reads this file at startup. If a site requires credentials but `.benchmark_secrets` does not contain the key, the task is SKIPPED with reason "credentials not configured."

### Recording Playwright Auth State

Auth state is recorded once by the benchmark operator, not by the CI runner. Steps:

1. Run `python -m benchmark.record_auth --site google_com --output .playwright_state/google_com.json`
2. This opens a headed Playwright browser and navigates to the sign-in page.
3. The operator manually signs in (including 2FA if required).
4. The auth state (cookies, localStorage, sessionStorage) is saved to `.playwright_state/{site_id}.json`.
5. Auth state files are gitignored. They are stored in a shared secure location (1Password, team vault) and downloaded to the CI runner via a CI secret.

**Auth state refresh:** Schedule a calendar reminder to refresh auth states every 14 days. On `BLOCKED_AUTH_EXPIRED` failure in nightly, the on-call engineer refreshes the auth state file for that site.

---

## Appendix B: Recorder Mode (for Anti-Bot Sites)

For sites where headless Playwright is reliably blocked (Flipkart, Amazon with anti-bot), the benchmark supports `recording_mode: recorded`. In this mode:

1. An operator runs the benchmark task ONCE in headed mode with auth restored.
2. The Playwright network interceptor records all HTTP requests/responses.
3. The recording is saved to `benchmark/recordings/{task_id}.har`.
4. In subsequent benchmark runs, Playwright serves the HAR recording via its HAR playback feature rather than making live network requests.

**Trade-offs of recording mode:**
- PRO: No anti-bot, no CAPTCHA, deterministic responses, fast.
- CON: Does not test against the live site. DOM changes since the recording was made are not caught. Recorded sites must be re-recorded when the site changes significantly.
- RULE: Never publish a benchmark baseline that uses recording mode without clearly labeling each task as `"mode": "recorded"` in the JSON report. Recording mode tasks are excluded from the failure taxonomy's BLOCKED_* categories.

---

## Appendix C: The Harness Self-Test

Before any real-site data is collected, the benchmark runner runs a self-test to verify the harness is working correctly. The self-test runs all 10 synthetic fixture tasks and asserts:

- Completion rate ≥ 90% (9 of 10 must pass)
- No INFRASTRUCTURE failures
- All `DOM_TEXT_PRESENT` criteria correctly evaluated
- All `URL_MATCHES` criteria correctly evaluated
- At least one `GROUNDING` failure detected (the self-test includes one task designed to fail grounding — the drag-drop fixture, which `executor_v2` cannot complete)

If the self-test fails, the benchmark aborts and reports HARNESS_ERROR. Real-site results are not collected until the harness self-test passes.

---

## Final Note: What to Expect from the First Run

The first M0 nightly run will likely show:

1. **Simple tier: 50–70% completion** — Most fixture tasks pass; some real-site tasks are blocked by CAPTCHA or login walls.
2. **Medium tier: 15–35% completion** — Multi-step tasks with dynamic inputs largely fail due to EXECUTION (synthetic events) and GROUNDING (hashed class names).
3. **Complex tier: 0–10% completion** — Cross-site and canvas tasks fail. This is expected and informative.
4. **Largest failure category: EXECUTION (30–50%)** — Confirming that M1 (CDP trusted driver) is the right next investment.
5. **Second largest: GROUNDING (15–30%)** — Confirming that wiring LocatorRanker matters.
6. **BLOCKED_CAPTCHA (10–20%)** — These are not failures; they are site defenses. Do not try to "fix" them.

This baseline is not a failure report. It is a precise diagnosis of exactly where and why the current system breaks. Every number in it points to a specific improvement in M1–M4. That is why this benchmark is milestone zero.

The goal is not to pass the benchmark on the first run. The goal is to have a number — any number — that is real, reproducible, and honest. Everything we build after today is measured against it.
