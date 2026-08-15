# Phase 0 Paired Baseline — 2026-08-15

This is the first paired Playwright/synthetic run produced from the same frozen 38-task dataset, backend revision, provider configuration, and host environment. It supersedes the 2026-08-14 run for current comparison, but does not overwrite or relabel the original raw baseline.

## Frozen denominator

- Suite: `phase0_baseline`
- Tasks: 38
- Fixtures: 12
- Auth-required tasks: 6
- Dataset SHA-256: `d60e41501d74e4acf502423e112c34119edfaa88e0718685e9895b39f3a5aa51`
- Joint `phase0_gate` result: zero errors

Blocked and skipped tasks are reported separately and are not successes. They are also excluded from the completion-rate denominator by the frozen benchmark contract.

## Results

| Metric | Playwright | Synthetic |
|---|---:|---:|
| Run ID | `m0-phase0_baseline-1786780435` | `m0-phase0_baseline-1786779876` |
| Duration | 317.2 s | 458.8 s |
| Completed | 16 | 14 |
| Counted denominator | 22 | 22 |
| Completion rate | 72.7% | 63.6% |
| Blocked | 9 | 9 |
| Skipped | 7 | 7 |
| Error | 4 | 3 |
| Failed | 0 | 2 |
| Timeout | 1 | 2 |
| Stuck | 1 | 1 |
| Step traces | 50 | 78 |
| HTML trace viewers | 19 | 20 |

The measured executor-fidelity gap is 9.1 percentage points. This is not a claim that Playwright is production behavior: Playwright is the trusted-input upper bound; synthetic execution is the current extension-fidelity path.

## Outcome differences

| Task | Playwright | Synthetic | Interpretation |
|---|---|---|---|
| `fixture__file_upload` | COMPLETED | FAILED / EXECUTION | Synthetic DOM events cannot assign a non-empty filename to a file input; native Playwright can. |
| `flipkart_com__product_filter` | COMPLETED | ERROR / INFRASTRUCTURE | Synthetic observation hit a transient null-body extraction failure during navigation. |
| `amazon_in__add_to_cart` | ERROR / INFRASTRUCTURE | FAILED / PLANNING | Live-site/navigation variance prevents an executor-only conclusion. |
| `cross_site__amazon_search_github_compare` | ERROR / INFRASTRUCTURE | TIMEOUT | Live-site/navigation variance prevents an executor-only conclusion. |

## Remaining counted failures — Playwright

| Task | Outcome | First attributable layer |
|---|---|---|
| `zomato_com__restaurant_search` | ERROR | Infrastructure: Chromium `ERR_HTTP2_PROTOCOL_ERROR` after bounded retry |
| `makemytrip_com__flight_search` | ERROR | Infrastructure: Chromium `ERR_HTTP2_PROTOCOL_ERROR` after bounded retry |
| `amazon_in__add_to_cart` | ERROR | Infrastructure: execution context destroyed during live navigation |
| `cross_site__amazon_search_github_compare` | ERROR | Infrastructure: execution context destroyed during live navigation |
| `amazon_in__product_search_price` | STUCK | Planning: repeated unverified report without new evidence |
| `booking_com__hotel_search` | TIMEOUT | Loop termination: maximum steps reached |

## Improvements relative to the original 2026-08-14 Playwright run

- Completion increased from 5/31 counted (16.1%) to 16/22 counted (72.7%). The denominators differ because the current harness explicitly classifies CAPTCHA, missing user input, and unavailable content as excluded blockers; compare raw counts as well as percentages.
- All eight original timeout-cluster tasks were resolved or reclassified: six complete, one blocks for missing user input, and one blocks because the referenced content is unavailable.
- The shared `Unsupported action_type ... search` 500 no longer occurs. The safe public form and Flipkart complete; Amazon and Booking now reach product-level planning/timeout states; remaining zero-step errors are concrete live-navigation failures.
- Unknown failures are eliminated. Browser `net::ERR_*` setup failures are classified as infrastructure, and transient HTTP/2/network-change/reset navigation errors receive one bounded retry.

## Verification

- Runtime inventory `--check`: passed.
- Frozen manifest gate: passed with zero errors and unchanged dataset SHA-256.
- Joint Playwright/synthetic report gate: passed with zero errors.
- Changed paths, benchmark suite, and policy contract: 243 tests passed.
- Entire backend repository: 4,406 passed and 25 failed. The residual failures are in legacy blueprint/feature-flag expectations, one popup integration test, one capability-count expectation, and one telemetry test. They are not hidden and are not represented as passing.

## Artifacts

- `backend/benchmark/reports/phase0-playwright-20260815.{json,md,html}`
- Playwright JSON SHA-256: `30d6351dd17dacca8694bd15b6da46a0ab750ac5099d4732494baa0ff5cce37b`
- `backend/benchmark/trace_out/m0-phase0_baseline-1786780435/`
- `backend/benchmark/reports/phase0-synthetic-20260815.{json,md,html}`
- Synthetic JSON SHA-256: `11edb12b17bea74954285f2f0a2470c8de8aee76b37df5bc2e9936b49e1c72b8`
- `backend/benchmark/trace_out/m0-phase0_baseline-1786779876/`

## Exit decision

The technical measurement gate is satisfied: the frozen denominator is unchanged, both executor modes have raw reports and traces, failure taxonomy is explicit, and no internal maturity label is used as production evidence. The project policy review is recorded in `policy-review-2026-08-15.md`, so Phase 1 implementation may begin under its mandatory enforcement conditions. This is not public-deployment approval. The 25 broader repository test failures are also carried forward as visible engineering debt, not silently waived.
