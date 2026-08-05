# Type 2 Browser Agent Core Architecture Audit

Date: 2026-08-05

## Product Class

AI Browser Assist is a Type 2 browser automation agent: an extension-first assistant that sits on top of Chrome or a remote browser and automates research, extraction, comparison, form filling, tab work, uploads/downloads, and evidence-based task completion.

It is not currently a Type 1 full AI browser like Comet, Atlas, Dia, or Gemini-in-Chrome. The extension-first path is still the correct near-term path because it validates browser automation capability before attempting a full browser shell.

## Current Stack

- Chrome Extension MV3.
- React 18, TypeScript, Vite, CRXJS.
- Content scripts for observation and execution.
- MV3 background service worker for browser messaging, tab control, downloads, and extension/backend handoff.
- FastAPI backend on Python 3.11.
- SQLAlchemy, Alembic, PostgreSQL via Docker.
- Pydantic settings and typed schema modules.
- LLM providers currently wired through backend service paths.
- Test stack: pytest for backend, Node test runner plus TypeScript type-check for extension.

## Current Core Shape

The application already has important Type 2 foundations:

- Side panel chat and action timeline.
- Browser observation from active tabs.
- Browser execution through extension content scripts.
- Manual and auto modes with safe/risky/critical separation.
- Planner Contract V2 outcomes: act, wait, ask, report, replan.
- Mission Ledger / Runtime V1 direction.
- Mission Blueprint models with objectives, evidence requirements, dependencies, and approval policy.
- Knowledge extraction artifacts and report artifacts.
- Multi-tab workspace and task workspace.
- Action verification, selector recovery, widget adapters, file transfer, and tab control.
- Benchmark and production validation task suites.

## Market Pattern

Browser Use, Skyvern, Browserbase/Stagehand, TinyFish, and similar systems converge on the same core loop:

1. Create a task/run/session.
2. Observe browser state using DOM, accessibility, and often screenshots.
3. Convert observation into a compact agent representation.
4. Plan the next semantic step.
5. Ground that step into executable browser actions.
6. Execute in a real browser.
7. Collect artifacts/evidence.
8. Validate goal progress.
9. Recover, replan, ask user, or complete.

Important market references:

- Browser Use emphasizes autonomous web interaction through Chromium/CDP, typed action schemas, tools, real browser profiles, max-step runs, cloud sessions, and custom tools.
- Skyvern uses screenshot plus DOM extraction, LLM planning, Playwright execution, structured extraction schemas, browser sessions, credentials, profiles, file operations, and validator feedback loops.
- Browserbase provides cloud browsers, search/fetch APIs, agent infrastructure, Stagehand-style natural language actions, self-healing automations, sessions, and serverless functions.
- TinyFish is infrastructure-first: search, fetch, browser sessions, and web-native agents for live web workflows.

## Main Architecture Diagnosis

The project is not missing "one more integration" like Browser Use or Skyvern. The main bottleneck is that several core agent responsibilities exist, but they are fragmented or only partially active.

The largest current risk is continuing to fix each validation task by patching the symptom. That makes the agent narrow because the same general capability is repeatedly rediscovered for every website.

## Core Gaps

### 1. Semantic Representation Is Not Yet Central

The app captures useful DOM, text, headings, content blocks, and elements, but the central runtime does not yet depend on one stable semantic page model.

Needed model:

- page type: search results, pricing page, jobs page, docs page, form, upload page, login page;
- entities: tool, company, job, price, plan, document, file, form field, search result;
- affordances: search box, result card, pagination, filter, upload input, submit button;
- result sets with rank, URL, title, snippet, source type;
- extracted facts with source URL and confidence.

### 2. Planner Still Does Too Much Low-Level Work

The planner should choose intent, not exact CSS selectors or brittle page-specific operations.

Target shape:

- planner says: "open top 5 relevant organic results";
- representation identifies search result objects;
- grounding chooses exact click/open-tab actions;
- execution performs browser operations;
- validation checks that 5 distinct source pages were opened.

### 3. Extraction Is Not First-Class Enough

The current Task 1 result proves this: the flow can open pages and produce a table, but field quality is heuristic. For Type 2, extraction must become schema-aware.

Needed:

- extraction schema compiled from user request;
- per-page extraction records;
- missing field handling;
- source attribution;
- confidence and validation;
- final artifact generation from records.

### 4. Mission Blueprint Is Promising But Not Yet the Main Controller

Mission Blueprint has the right primitives: nodes, dependencies, evidence requirements, expansion rules, approval policy. But runtime still behaves like a planner loop plus patches.

Needed:

- convert user request into mission blueprint;
- execute blueprint nodes through ledger intents;
- mark nodes satisfied only from evidence;
- keep planner as reasoner/replanner, not queue owner.

### 5. Policy and Safety Are Scattered

Manual/auto mode and approval rules exist, but policy should be centralized.

Needed:

- one risk classifier for actions, data movement, auth, upload/download, submission, payment, deletion, and messaging;
- one policy decision object: allow, auto_allow, require_approval, require_user_handoff, block;
- policy checked before execution, not only in UI.

### 6. Visual Fallback Is Missing

Do not build this first, but acknowledge it. Skyvern/Operator-style agents use screenshots because real pages often hide meaning from DOM. This is P1 after semantic representation and schema extraction are stable.

## Do We Need To Implement Browser Use, Skyvern, Or Scraping Tools?

Not as dependencies right now.

We should not bolt Browser Use or Skyvern into the app as the main runtime yet. That would create two competing agents and make Mission Ledger authority weaker.

Better approach:

- Borrow architecture patterns.
- Keep our extension as the browser executor.
- Keep Runtime V1 / Mission Ledger as the authority.
- Add provider interfaces later, so Browser Use, Skyvern, Browserbase, or TinyFish can become optional execution/extraction providers for specific tasks.

Possible future provider roles:

- Browser Use provider: remote/browser-runner fallback for hard automation.
- Skyvern provider: form-heavy workflow fallback with visual reasoning.
- Browserbase/TinyFish provider: search/fetch/browser infrastructure for scalable cloud execution.

But the core should remain ours.

## First Core Build Slice

Build a Generic Research and Extraction Core before continuing broad task validation.

This directly supports Validation Tasks 1, 2, 4, 5, 6, and 10, and prepares for LinkedIn/jobs and SaaS workflows.

### Slice A: Research Mission Schema

Create a deterministic mission schema for research/comparison/extraction tasks:

- objective;
- query;
- source_count;
- source_policy;
- required_fields;
- output_format;
- evidence_requirements;
- completion_criteria.

### Slice B: Search Result Semantic Model

Promote search result understanding into a stable model:

- result_id;
- rank;
- title;
- url;
- snippet;
- source_domain;
- is_ad;
- is_search_vertical;
- relevance_score;
- opened_tab_id / opened_url evidence.

### Slice C: Schema-Aware Extraction

For each opened source page, extract fields requested by the mission:

- field name;
- value;
- source quote or source text span where safe;
- source URL;
- confidence;
- missing reason.

For Task 1:

- Tool;
- Purpose;
- Pricing;
- Limitation;
- URL.

### Slice D: Artifact Builder

Generate final output only from validated extraction records, not from raw page text.

### Slice E: Completion Gate

Mission is complete only when:

- enough distinct sources were opened;
- required fields are either filled or explicitly marked not mentioned;
- final artifact exists;
- artifact has source URLs;
- no critical policy violation occurred.

## Architecture Rule Going Forward

When a validation task fails, classify the failure before patching:

- observation failure;
- semantic representation failure;
- grounding failure;
- execution failure;
- extraction failure;
- validation/completion failure;
- UI/reporting failure;
- policy failure.

Only fix the first failing layer. If the same layer fails across multiple tasks, build the generic layer instead of a task-specific patch.

## Recommended Next Implementation

Implement `ResearchMissionSpec` and a schema-aware extraction path for research/comparison missions, then rerun Validation Task 1.

Acceptance criteria:

- Task 1 output table has exactly five rows from five distinct non-Google URLs.
- Each row is generated from an `ExtractionRecord`.
- Missing pricing/limitation is represented as `Not mentioned`.
- The final table is built by the artifact builder.
- Mission completion depends on extraction records and source count, not only planner text.

