# Mission Blueprint V1 Benchmark & Validation Suite

## Purpose

This benchmark suite is the permanent regression gate for Mission Blueprint V1 quality before Wave 4.

It validates Blueprint behavior only. It does not change Runtime V1 behavior, execute providers, call Browser Control, invoke the planner, or evaluate mission completion.

## Scope

Implemented in:

- `backend/tests/unit/test_mission_blueprint_benchmark_v1.py`

The suite covers:

- Research
- Shopping
- Booking
- Authentication
- Navigation
- File Upload
- File Download
- Form Filling
- Data Extraction
- Multi-tab Research
- Dashboard Analysis
- Job Application
- Email Drafting
- Calendar Scheduling
- Cross-System Workflow

## Benchmark Catalog

Each benchmark mission defines:

- user goal
- expected mission classification
- expected capabilities
- expected Blueprint nodes
- expected dependency edges
- expected READY nodes
- expected blocked nodes
- expected clarification requirements
- expected risk annotations
- expected expansion behavior
- expected ledger intent provenance

Current Mission Intelligence maps the catalog into the four supported Mission Blueprint V1 mission classes:

- `research`
- `navigation`
- `data_extraction`
- `file_processing`

This is intentional. The catalog validates current architecture while exposing where future Blueprint waves should improve mission-specific decomposition quality.

## Validation Framework

The benchmark performs three levels of validation.

### 1. Blueprint Quality

For every benchmark, the suite builds a Blueprint and validates:

- Mission Understanding
- Mission Classification
- Capability Mapping
- Dependency Graph
- Clarification Detection
- Risk Annotation
- Blueprint Validation
- Readiness Evaluation
- Critical Path
- Unreachable Nodes

Failure categories are explicit:

- missing nodes
- incorrect dependencies
- incorrect capabilities
- unnecessary clarifications
- missing clarifications
- unreachable nodes
- invalid critical path

### 2. Expansion & Ledger Provenance

For every benchmark, the suite persists the Blueprint, saves a readiness snapshot, and expands READY nodes.

It verifies:

- only READY nodes expand
- expansion is idempotent
- duplicate ledger intents are not created
- generated intents retain `blueprint_id`
- generated intents retain `blueprint_node_id`
- generated intents retain `blueprint_revision`
- generated intents remain `QUEUED`

This proves Blueprint creates executable work while Runtime V1 remains the only execution authority.

### 3. Coverage & Scoring

Every benchmark receives a score across:

- classification
- capabilities
- node graph
- dependency graph
- readiness
- blocking state
- clarification detection
- risk annotation

Acceptance thresholds:

- each benchmark score must be at least `0.85`
- average catalog score must be at least `0.95`

## Known Quality Findings

The current risk annotator is keyword-based. The benchmark records current behavior, including known false positives such as:

- `headphones` matching the `phone` privacy keyword
- `buying table` matching the payment keyword

These are not runtime failures. They are future Mission Intelligence quality improvements.

## Future Regression Strategy

Before Wave 4 or any Mission Intelligence change:

1. Run the benchmark suite.
2. Review failures by category.
3. Update expectations only when the approved architecture intentionally changes Blueprint quality.
4. Never weaken the suite to hide regressions.

Recommended command:

```powershell
cd backend
.venv-codex\Scripts\python.exe -m pytest tests\unit\test_mission_blueprint_benchmark_v1.py -q
```

For broader safety:

```powershell
cd backend
.venv-codex\Scripts\python.exe -m pytest tests\unit\test_mission_blueprint_benchmark_v1.py tests\unit\test_mission_blueprint_expansion_v3b.py -q
```

