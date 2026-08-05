# First 10 Validation Tasks Readiness Report

Date: 2026-08-05

## Purpose

This report evaluates whether the current Type 2 browser automation assistant is ready to run the first 10 validation tasks as a batch.

The purpose is not to patch one task. The purpose is to identify missing generic capabilities before live execution, then build the core layers that allow many tasks to improve together.

## Task Readiness Summary

Current readiness:

- Ready: 0 / 10
- Partial: 8 / 10
- Missing core capability: 1 / 10
- Environment-dependent: 1 / 10

This does not mean the app cannot attempt the tasks. It means the app should not be judged as production-capable for the full first-10 suite yet because several shared capabilities are still partial.

## Cross-Task Bottlenecks

### 1. Schema-Aware Extraction

Affected tasks: 1, 2, 4, 5, 6, 10.

Status: partial.

Current capability:

- Extraction records exist.
- Research missions now have explicit fields, source count, and completion criteria.
- Missing pricing/limitation can be represented as `Not mentioned`.

Gap:

- Values are still heuristic.
- No source-span/citation per field.
- No page-type-specific extractors for jobs, pricing pages, documentation pages, directories, or best-practice articles.

Generic fix:

Build field extractors with:

- value;
- source URL;
- source text span;
- field confidence;
- missing reason;
- entity type.

### 2. Multi-Tab Source Coverage

Affected tasks: 1, 3, 4, 10 plus other research tasks.

Status: partial.

Current capability:

- Extension can open tabs.
- Timeline can show opened-tab and tab-switch evidence.
- Multi-tab workspace exists.

Gap:

- Source coverage is not yet a central reusable completion criterion across all research and extraction missions.
- The mission should know which source page satisfied which evidence requirement.

Generic fix:

Unify opened-tab evidence with Mission Blueprint nodes and Mission Completion criteria.

### 3. Search Result Collection and Ranking

Affected tasks: 1, 3, 4, 10.

Status: partial.

Current capability:

- Browser intelligence can collect SERP candidates and dedupe some duplicate URLs.

Gap:

- No reusable `SearchResult` model with organic/ad/source type/relevance.
- No deterministic ranking/coverage policy.
- No official-source preference for documentation tasks.

Generic fix:

Promote `SearchResult` to a semantic object:

- rank;
- title;
- URL;
- snippet;
- domain;
- source type;
- ad/organic;
- relevance score;
- opened tab evidence.

### 4. Domain Entity Semantics

Affected tasks: 2, 4, 5, 10.

Status: partial.

Missing entity models:

- `JobPosting`
- `PricingPlan`
- `DocumentationPage`
- `DirectoryEntry`
- `BestPracticeSource`

Generic fix:

Add typed extraction/entity models instead of relying on generic paragraph search.

### 5. Directory Pagination / Collection Policy

Affected task: 6.

Status: missing.

Gap:

- No generic policy for multi-page directories, pagination, infinite scroll, dedupe, stop conditions, and record accumulation.

Generic fix:

Build `CollectionPolicy`:

- detect result/item cards;
- detect next-page controls;
- collect records per page;
- dedupe by URL/title/entity key;
- stop by requested count, max pages, or no new records.

### 6. Form and Signup Policy

Affected tasks: 7, 9.

Status: partial.

Current capability:

- Fill/click execution exists.
- Manual/auto approval distinction exists.
- Critical actions require approval.

Gap:

- No central `FormWorkflowSpec`.
- Signup/account-creation stop rules are not deterministic enough.
- Fake-data broker is not first-class.

Generic fix:

Build:

- form field schema;
- fake data provider;
- stop-before-submit/review-page policy;
- critical submit/account/payment guards.

### 7. File Upload Broker

Affected task: 8.

Status: partial.

Current capability:

- File transfer modules exist.

Gap:

- No single upload broker for approved file handles, filename evidence, widget acceptance evidence, and upload result reporting.

Generic fix:

Build a file broker around upload intents and upload evidence.

### 8. Batch Live Runner

Affected all tasks.

Status: missing.

Gap:

- No production extension batch runner for the first 10 tasks with per-task artifacts, budgets, approvals, and taxonomy output.

Generic fix:

Build a controlled batch runner that:

- launches the extension once;
- runs all 10 prompts sequentially;
- records timelines and mission evidence;
- stops each task at criteria/budget/blocker;
- emits task status and failure taxonomy.

## Recommended Build Order

1. Search result semantic model and source ranking.
2. Schema-aware extraction with field-level evidence.
3. Typed entity extractors: pricing, docs, jobs.
4. Collection policy for pagination/directories.
5. Form workflow spec and safety policy.
6. File upload broker.
7. Batch live runner for all 10 tasks.

## What Not To Do

- Do not integrate Browser Use or Skyvern as the main runtime.
- Do not patch specific websites first.
- Do not run all 10 tasks manually and call failures "planner bugs" without taxonomy.
- Do not let final answers complete without evidence-backed criteria.

## Next Engineering Step

Build the shared semantic/extraction core before live batch testing:

1. `SearchResult` semantic model.
2. `SourceCoverage` mission evidence.
3. Field-level `ExtractionRecord` evidence.
4. Research/source completion criteria using those objects.

Then run all 10 tasks in a controlled batch and classify remaining failures.

