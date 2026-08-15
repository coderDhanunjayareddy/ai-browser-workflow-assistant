# Phase 0 Planning-Cluster Delta — 2026-08-15

## Scope

This cycle investigated the 10 tasks classified as `PLANNING` in run `m0-phase0_baseline-1786728413`. It did not change the frozen task dataset or overwrite the original baseline.

## Root causes and fixes

| Root cause | Baseline impact | Fix |
|---|---:|---|
| Completed non-browser intent had no `suggested_actions` | 5 immediate `no action suggested` failures | Parse successful `intent_execution` receipts as backend progress, record the step, and request the next planner turn |
| `open_new_tab` used locator resolution | 2 repeated empty-selector failures | Create a Playwright page directly, navigate to the validated HTTP(S) URL, and focus the new page |
| Visible fixture evidence fell through to planning | 3 fixture failures | Ground invoice reporting, first-row Edit, and dynamically observed Ready controls from current page evidence |
| Multi-source count phrases defaulted to one | Premature one-source report in pricing workflow | Recognize products, tools, and websites plus phrases such as “3 different tools” |
| Identical unverified reports could repeat to `max_steps` | 34 duplicate reports in one rerun | Stop as `STUCK` after three identical report/evidence/criteria signatures |

## Traced rerun results

| Task | Targeted result | Evidence |
|---|---|---|
| `fixture__invoice_total_report` | COMPLETED, 1 step | `m0-phase0_baseline-1786774983` |
| `fixture__table_edit` | COMPLETED, 1 step | `m0-phase0_baseline-1786774986` |
| `fixture__dynamic_load` | COMPLETED, 1 step | `m0-phase0_baseline-1786774988` |
| `first10__01_search_ai_browser_tools` | BLOCKED_CAPTCHA, 0 steps | `m0-phase0_baseline-1786775005` |
| `first10__02_hyderabad_careers_extract` | BLOCKED_CAPTCHA, 0 steps | `m0-phase0_baseline-1786775013` |
| `first10__04_ai_code_assistant_pricing` | TIMEOUT after progressing through native new-tab execution; subsequent verification BLOCKED_CAPTCHA | `m0-phase0_baseline-1786775018`, `m0-phase0_baseline-1786775218` |
| `first10__05_browser_automation_docs` | BLOCKED_CAPTCHA, 0 steps | `m0-phase0_baseline-1786775039` |
| `first10__06_directory_multipage_collection` | BLOCKED_CAPTCHA, 0 steps | `m0-phase0_baseline-1786775045` |
| `first10__08_real_file_upload` | BLOCKED_CAPTCHA, 0 steps | `m0-phase0_baseline-1786775051` |
| `first10__10_ai_browser_testing_best_practices` | BLOCKED_CAPTCHA, 0 steps | `m0-phase0_baseline-1786775058` |

The first fixture rerun attempt was discarded because the local backend was down and every task received the same connection-refused `AnalyzeError(503)`. After restarting the backend and obtaining three consecutive HTTP 200 health checks, the unchanged fixture reruns all completed.

## Interpretation

The three deterministic failures are verified conversions from planning failure to completion. The new-tab contract is verified by the pricing trace: step 0 navigated to `https://codeassist.google/products/business` successfully instead of failing empty-selector grounding.

The six CAPTCHA results and the final pricing verification are environmental blocks, not passes or product failures. Therefore this cycle does not recalculate the frozen 16.1% completion rate. A complete comparable rerun requires a search surface that is not presenting a challenge page.
