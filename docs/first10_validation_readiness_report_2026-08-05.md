# First 10 Validation Tasks Readiness Report

Date: 2026-08-05

## Purpose

This report evaluates whether the current Type 2 browser automation assistant is ready to run the first 10 validation tasks as a batch.

The purpose is not to patch one task. The purpose is to identify missing generic capabilities before live execution, then build the core layers that allow many tasks to improve together.

## Task Readiness Summary

Current readiness:

- Ready: 0 / 10
- Partial: 9 / 10
- Missing core capability: 0 / 10
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
- Extraction records now include field-level source evidence with source URL, source text, confidence, source kind, and missing reason.
- Extraction records now include typed entity metadata for research sources, pricing plans, documentation pages, job postings, directory entries, form results, and file results.

Gap:

- Values are still heuristic.
- Page-type-specific extraction is present as a foundation, but not robust enough yet for production validation across real job boards, pricing tables, documentation sections, directories, or best-practice articles.

Generic fix:

Harden typed field extractors for job postings, pricing plans, documentation pages, directory entries, forms, uploads, and best-practice sources.

### 2. Multi-Tab Source Coverage

Affected tasks: 1, 3, 4, 10 plus other research tasks.

Status: partial.

Current capability:

- Extension can open tabs.
- Timeline can show opened-tab and tab-switch evidence.
- Multi-tab workspace exists.
- Backend mission completion now checks requested distinct source count, so duplicated evidence from one URL cannot satisfy a multi-source research mission.

Gap:

- Opened-tab evidence is not yet fully unified with mission blueprint nodes across all research and extraction missions.
- The mission should know which source page satisfied which evidence requirement.

Generic fix:

Unify opened-tab evidence with Mission Blueprint nodes and Mission Completion criteria.

### 3. Search Result Collection and Ranking

Affected tasks: 1, 3, 4, 10.

Status: partial.

Current capability:

- Browser intelligence can collect SERP candidates and dedupe some duplicate URLs.
- Search results now carry semantic metadata such as normalized URL, source domain, source type, ad flag, and relevance score.

Gap:

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

Typed extraction/entity models now exist as a foundation. Next, harden field extraction and source coverage so the entities are reliable on real pages instead of only heuristic paragraph matches.

### 5. Directory Pagination / Collection Policy

Affected task: 6.

Status: partial.

Current capability:

- `CollectionPolicy` exists for collection/list/directory missions.
- It detects item candidates from links and directory-like text.
- It detects next-page, numbered-page, and load-more style pagination candidates.
- It tracks stop conditions: requested count, max pages, no new items, and no next page.
- Item-level directory records now use collection item keys for dedupe, so multiple entries from the same page can survive validation.
- Passive Mission Blueprint nodes now include `collect_page_items` and `advance_pagination` for directory collection goals.
- Backend orchestration now converts a continuing `CollectionPolicy` state into a safe next-page `navigate` action before the Mission Ledger bridge, so the extension receives durable `intent_id` and `mission_id`.

Gap:

- Live multi-page browser validation still needs to prove the loop across real pages.
- Timeline evidence does not yet show per-page collection progress and final stop reason from the policy.

Generic fix:

Validate and harden `CollectionPolicy` in extension execution:

- run the next-page loop against a real paginated directory;
- confirm item evidence accumulates across pages;
- emit per-page item count, next URL, and final stop reason in timeline evidence.

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

1. Source ranking and source coverage policy using the semantic `SearchResult` model.
2. Harden schema-aware extraction with field-level evidence.
3. Harden typed entity extractors: pricing, docs, jobs, directories, forms, uploads.
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

1. `SearchResult` semantic model. Done.
2. `SourceCoverage` mission evidence. Done for backend distinct-source completion; extension tab-to-source unification remains.
3. Field-level `ExtractionRecord` evidence. Done.
4. Typed page/domain extractor foundation. Done; hardening remains.
5. Research/source completion criteria using those objects.

Then run all 10 tasks in a controlled batch and classify remaining failures.
