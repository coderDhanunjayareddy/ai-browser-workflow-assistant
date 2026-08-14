# Phase 0 — Freeze and Measure

Phase 0 establishes a trustworthy baseline before browser autonomy expands. It does not add a new planner, executor, governance subsystem, or product surface.

## Exit gate

Phase 0 is complete only when all of the following are true:

- the subsystem freeze is active and exceptions are documented;
- the generated runtime inventory is current and every source module has one status;
- the frozen 38-task baseline has valid Playwright and synthetic reports;
- raw task traces exist for both executor modes;
- skipped and blocked tasks are not counted as successful;
- critical-action and sensitive-data definitions are reviewed;
- baseline metrics are published without treating internal maturity labels as production evidence.

Current status is tracked in [status.md](status.md).

## 1. Subsystem freeze

Until the Phase 0 exit gate passes:

- do not add a new top-level package under `backend/app` or `extension/src`;
- do not add a new planner, runtime, registry, persistence layer, policy engine, execution gateway, or capability catalog;
- do not add new capability IDs to `shared/v4_browser_capabilities.json`;
- do not label shadow, fixture-only, test-only, stub, or metadata-only behavior as production-ready;
- fixes may deepen an existing live path, improve measurement, repair security, or remove duplication;
- an exception must name the Phase 0 blocker it resolves, identify the live caller, include an end-to-end test, and update the runtime inventory.

The freeze is a scope rule, not a ban on fixing the current system.

## 2. Runtime inventory

Generate the complete source-file inventory:

```powershell
cd backend
.venv-codex\Scripts\python.exe tools\phase0_runtime_inventory.py `
  --json ..\docs\phase0\runtime-inventory.json `
  --markdown ..\docs\phase0\runtime-inventory.md
```

Check that committed outputs are current:

```powershell
.venv-codex\Scripts\python.exe tools\phase0_runtime_inventory.py `
  --json ..\docs\phase0\runtime-inventory.json `
  --markdown ..\docs\phase0\runtime-inventory.md `
  --check
```

Status meanings:

- `live`: statically reachable from a current product entry root;
- `shadow`: registered/reachable code outside the core extension request path;
- `test-only`: referenced by tests but not current product roots;
- `stub`: source explicitly identifies itself as a stub or no-op;
- `dead`: not statically reachable from configured roots.

`dead` is not deletion approval. Check dynamic imports and feature flags first.

## 3. Frozen baseline suite

`backend/benchmark/suites/phase0_baseline.yaml` explicitly freezes 38 tasks. It intentionally does not inherit every future scenario automatically.

Validate and publish the dataset manifest without opening a browser:

```powershell
cd backend
.venv-codex\Scripts\python.exe -m benchmark.phase0_gate `
  --manifest-output benchmark\reports\phase0-manifest.json
```

Run both executor modes with raw tracing:

```powershell
$env:TRACE_MODE='true'
.venv-codex\Scripts\python.exe -m benchmark.m0_runner `
  --suite phase0_baseline --executor playwright --headless --trace `
  --output benchmark\reports\phase0-playwright.json

.venv-codex\Scripts\python.exe -m benchmark.m0_runner `
  --suite phase0_baseline --executor synthetic --headless --trace `
  --output benchmark\reports\phase0-synthetic.json
```

Validate the two raw reports against the frozen denominator:

```powershell
.venv-codex\Scripts\python.exe -m benchmark.phase0_gate `
  --playwright-report benchmark\reports\phase0-playwright.json `
  --synthetic-report benchmark\reports\phase0-synthetic.json
```

Reports are written as JSON, Markdown, and HTML. Per-task trace viewers are written beneath `backend/benchmark/trace_out/<run_id>/<task_id>/viewer.html`. Authentication state is local and ignored by Git; missing authentication must produce `SKIPPED`.

## 4. Policy definitions

The machine-readable contract is `backend/app/policy/phase0_taxonomy.py`; the review document is [critical-actions-and-sensitive-data.md](critical-actions-and-sensitive-data.md).

This taxonomy defines future execution-gate behavior but does not itself authorize or execute an action. Live enforcement belongs to Phase 1.

## 5. Required baseline publication

Publish these artifacts together:

- dataset manifest and SHA-256;
- Playwright raw JSON/Markdown/HTML report;
- synthetic raw JSON/Markdown/HTML report;
- trace directory for both runs;
- environment metadata: commit, dirty-tree state, provider/model, extension build, Chrome version, operating system, auth availability, and run time;
- metric summary with blocked/skipped separated from agent failures;
- top failure categories and the first wrong decision for every failed/partial task.

