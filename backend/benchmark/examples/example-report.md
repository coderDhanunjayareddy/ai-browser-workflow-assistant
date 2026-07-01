> # ⚠️ EXAMPLE REPORT — SYNTHETIC DATA — NOT A REAL BASELINE
>
> This file exists only to show what an M0 report looks like. The numbers are
> **fabricated**, not measured. It was **not** produced by `m0_runner`.
> **The only valid baseline is produced by `m0_runner` and stored in `benchmark/baselines/`.**

---

# M0 Benchmark Report — m0-SAMPLE-synthetic

**Suite:** nightly | **Executor:** playwright | **Duration:** 612s

## Summary

| Metric | Value |
|---|---|
| Task Completion Rate | **40.0%** |
| 95% CI | [16.8%, 68.7%] |
| Simple tier | 100.0% (4/4) |
| Medium tier | 0.0% (0/3) |
| Complex tier | 0.0% (0/3) |
| Step Success Rate | 83.3% |
| Human Intervention Rate | 0.0% |
| Recovery Success Rate | 0.0% |
| Validation Pass Rate | 83.3% |
| Estimated Cost | $0.01 |

## Completed
- [COMPLETED] Fixture: fixture__login_form (simple/FORM_SUBMIT, 4 steps)
- [COMPLETED] YouTube: youtube_com__video_search (simple/SEARCH, 3 steps)
- [COMPLETED] GitHub: github_com__repo_search (simple/SEARCH, 3 steps)
- [COMPLETED] Fixture: fixture__pagination (simple/PAGINATION, 3 steps)

## Failed
- [FAILED] Amazon India: amazon_in__product_search_price (medium/SEARCH, 3 steps) — EXECUTION: sample failure detail
- [FAILED] Flipkart: flipkart_com__product_filter (medium/FILTER, 3 steps) — GROUNDING: sample failure detail
- [FAILED] Google Docs: docs_google_com__create_type (medium/FORM_SUBMIT, 3 steps) — VISION_REQUIRED: sample failure detail
- [TIMEOUT] Amazon India: amazon_in__add_to_cart (complex/MULTISTEP, 6 steps) — TIMEOUT: sample failure detail
- [FAILED] Cross-Site: cross_site__amazon_search_github_compare (complex/CROSS_SITE, 8 steps) — ORCHESTRATION: sample failure detail [expected-failure]
- [FAILED] Google Sheets: sheets_google_com__enter_data (complex/FORM_SUBMIT, 3 steps) — VISION_REQUIRED: sample failure detail [expected-failure]

## Blocked / Skipped
- [BLOCKED] Booking.com: booking_com__hotel_search (medium/SEARCH, 3 steps) — BLOCKED_CAPTCHA: sample failure detail

## Failure Distribution
| Category | Count |
|---|---|
| VISION_REQUIRED | 2 |
| EXECUTION | 1 |
| GROUNDING | 1 |
| BLOCKED_CAPTCHA | 1 |
| TIMEOUT | 1 |
| ORCHESTRATION | 1 |

## Locator Strategy Success
| Strategy | Resolutions |
|---|---|
| css_selector | 36 |
| accessibility_name | 3 |
| data_testid | 3 |

## Recommendations
- Largest failure category: VISION_REQUIRED (2/7 = 29%).
- VISION_REQUIRED dominates — M3 (visual grounding) is needed for these tasks.
- Recovery success rate is 0% — M2 (closed loop with recovery) is unblocked.
- 9% of tasks blocked by CAPTCHA — site defenses, not agent failures.