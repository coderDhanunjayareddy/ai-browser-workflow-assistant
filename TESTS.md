# Test and evaluation plan

## What counts as success

Current prerequisite task evidence (2026-10-06): 14 focused backend tests, 256 extension tests, extension type-check, and build passed. The broad backend suite reported 3,811 passed and one mission-ledger replay failure; that single test passed immediately when rerun alone, so the suite-level failure remains unclassified. Two known stale inventory/fixture-count checks were excluded. The full MakeMyTrip side-panel diagnostic has **not** passed. `PREREQ-12` opened the date picker through the application; `PREREQ-13` observed the exact 20 October grid cell. The parser was then fixed, but `PREREQ-14` to `PREREQ-16` encountered `ERR_HTTP2_PROTOCOL_ERROR` on initial navigation. See `docs/failure-log.md`. Live date selection, traveler-count and result-list verification, and the human boundary check remain required.

For live failures, run the full diagnostic task through the application before changing runtime code. Start from a blank tab when destination discovery is under test. The test driver supplies the task and observes; it does not repair page state, choose the site, or perform browser steps for the assistant. Record the first failure, then implement a general fix and rerun the same task through the side panel.

At a human step, keep the same browser profile, tab, and extension workflow open. Notify the owner and wait for them to complete the step. Resume using the application's own control, then verify that the task continues from its checkpoint without duplicate earlier actions. Count any driver closure at the handoff as a test-infrastructure failure.

A task passes only when the real side panel reaches the requested end state and records independent final evidence. A clicked button, a plausible AI answer, a search result, or a payment page is not a completed booking. Distinguish product failure from site/network blockage.

## Manual test cases

| Case | Expected result |
|---|---|
| Navigate, search, choose exact result | Correct page and item identity; no related-item substitution. |
| Dynamic city/date/traveler controls | Selected values remain visible after the widget closes. |
| Multi-step form with delayed validation | Errors are shown and fixed or reported; no silent submit success. |
| Popup or new tab | Active tab and task identity remain correct. |
| Login or CAPTCHA | Human handoff; no automatic bypass. |
| Final no-charge test booking | Exact details shown for approval; one submission; confirmation evidence recorded. |
| Payment-required flow | Stop before payment and report incomplete. |
| Reload or worker restart | Resume from verified state; no duplicate final submission. |
| Missing/ambiguous target or changed page | Re-observe or stop; never click an approximate alternative. |

## Automated plan

- Extension: run `npm run type-check`, `npm test`, and `npm run build` from `extension/` for runtime changes.
- Backend: run focused tests for touched modules, then the broader relevant suite. Use the repository's existing Python test setup; diagnose failures before adding features.
- Controlled browser fixtures: loading delay, duplicate labels, popups, date picker, form error, stale target, repeated no-effect, restart, and uncertain final submission.
- Real side-panel runs: use one canonical build and record every step. Standalone Playwright actions are not release evidence.

## Benchmark tasks and metrics

Use the existing hotel and flight **search** scenarios as partial diagnostics, not proof of booking. Add a complete no-charge booking fixture and, after scope approval, a representative live workflow with permitted test details.

Track final-goal pass rate, wrong target, duplicate effect, false success claim, confirmation recall, privacy violation, first-failure category, retries, no-effect steps, elapsed time, AI calls, and cost. Before release, set an explicit consecutive-run gate for the selected workflow; a failed run resets the streak. Keep raw evidence and a short root-cause entry in `docs/failure-log.md`.
