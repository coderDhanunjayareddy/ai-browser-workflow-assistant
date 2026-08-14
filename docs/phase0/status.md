# Phase 0 Status

**Started:** 2026-08-14  
**State:** In progress

| Deliverable | Status | Evidence |
|---|---|---|
| Subsystem freeze | Implemented | `docs/phase0/README.md` |
| Complete runtime map | Implemented, pending review | Generated JSON and Markdown inventories |
| Frozen 25–50 task suite | Implemented | 38 explicit tasks in `phase0_baseline.yaml` |
| Dataset audit and fingerprint | Implemented | 38 tasks; SHA-256 `d60e41501d74e4acf502423e112c34119edfaa88e0718685e9895b39f3a5aa51` |
| Raw Playwright baseline | Published | Run `m0-phase0_baseline-1786728413`; JSON/Markdown/HTML report plus 104 step traces |
| Raw synthetic baseline | Pending environment run | Requires healthy backend, configured model, browser/network |
| Critical-action policy | Implemented, pending product/security review | `phase0_taxonomy.py` and policy document |
| Sensitive-data policy | Implemented, pending product/security review | `phase0_taxonomy.py` and policy document |
| Exit gate | Not met | Playwright completion is 16.1%; synthetic baseline and policy/review sign-off remain |

Internal capability maturity metadata is not accepted as production evidence. The Phase 0 gate uses only executed task outcomes and raw traces.

## First harness gate — 2026-08-14

- Backend: healthy; database connected.
- Provider: configured (secret value not recorded).
- Playwright: available.
- Self-test: **failed** — 0/3 fixture tasks completed; all reached their step limit; no infrastructure errors.
- Traced diagnostic: `fixture__login_form`, Playwright mode, 0/1 completed, five steps, `TIMEOUT`.
- First wrong decision: the blueprint emitted `navigate` without a URL even though the runner had already opened the fixture start page.
- Consequence: execution failed with `navigate: no url`; the semantic phase stayed `OPEN`, rejected subsequent `fill`, exhausted retries, and reached `max_steps`.
- Runner lifecycle issue: the report completed, but the traced CLI process did not exit and required termination.

Decision: do not run or publish the 38-task real-site baseline until the fixture self-test reaches at least 90% with zero infrastructure errors. See [harness-diagnostic-2026-08-14.md](harness-diagnostic-2026-08-14.md).

## Repaired harness gate and first raw baseline — 2026-08-14

- Regression suites: 57 focused blueprint/orchestrator tests, 67 broader orchestrator/benchmark tests, 99 observed-control/kernel/orchestrator tests, and 67 final pagination-recovery tests passed in their respective runs.
- Stable backend check: three consecutive `/health` responses returned HTTP 200.
- Final unchanged fixture self-test: **passed** — 3/3 completed (100%), zero infrastructure errors, clean process exit.
- Frozen Playwright run: `m0-phase0_baseline-1786728413`, 38 tasks attempted in 466.2 seconds.
- Counted result: 5/31 completed (16.1%, 95% CI 7.09%–32.63%); 7 tasks skipped for unavailable auth or controlled-account prerequisites.
- Remaining outcomes: 14 failed, 8 timed out, 2 stuck, and 2 ended with runner errors.
- Failure distribution: 10 planning, 8 timeout, 6 infrastructure, and 2 unknown.
- Structural Phase 0 gate: passed with 38 frozen tasks, 12 fixtures, 6 auth-required tasks, dataset SHA-256 `d60e41501d74e4acf502423e112c34119edfaa88e0718685e9895b39f3a5aa51`, and zero manifest errors.
- Raw artifacts: `backend/benchmark/reports/phase0-baseline-20260814.{json,md,html}` and `backend/benchmark/trace_out/m0-phase0_baseline-1786728413/` (31 executed-task directories, 104 step traces, 28 HTML viewers).

Decision: the measurement harness is now trustworthy enough to expose the product baseline, but the Phase 0 exit gate is **not** met. The 16.1% completion rate is the baseline to improve, not a production-readiness claim. See [playwright-baseline-2026-08-14.md](playwright-baseline-2026-08-14.md).
