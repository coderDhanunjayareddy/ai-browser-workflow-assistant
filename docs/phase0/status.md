# Phase 0 Status

**Started:** 2026-08-14  
**State:** Complete — Phase 0 exit gate passed

| Deliverable | Status | Evidence |
|---|---|---|
| Subsystem freeze | Implemented | `docs/phase0/README.md` |
| Complete runtime map | Implemented and current | Generated JSON and Markdown inventories; `--check` passes |
| Frozen 25–50 task suite | Implemented | 38 explicit tasks in `phase0_baseline.yaml` |
| Dataset audit and fingerprint | Implemented | 38 tasks; SHA-256 `d60e41501d74e4acf502423e112c34119edfaa88e0718685e9895b39f3a5aa51` |
| Raw Playwright baseline | Published | Current run `m0-phase0_baseline-1786780435`; 16/22 counted complete (72.7%) |
| Raw synthetic baseline | Published | Run `m0-phase0_baseline-1786779876`; 14/22 counted complete (63.6%) |
| Critical-action policy | Approved for Phase 1 implementation | Taxonomy, policy contract, tests, and `policy-review-2026-08-15.md` |
| Sensitive-data policy | Approved for Phase 1 implementation | Taxonomy, policy contract, tests, and `policy-review-2026-08-15.md` |
| Exit gate | Passed | Technical measurement and project governance gates complete; Phase 1 enforcement conditions recorded |

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

## Planning-cluster improvement cycle — 2026-08-15

The 10 baseline failures classified as `PLANNING` were traced to three shared contract defects:

1. completed backend-only intents were treated as missing browser actions by the benchmark loop;
2. Playwright routed URL-backed `open_new_tab` through selector lookup with an empty selector;
3. observed invoice, table-edit, and dynamically loaded controls fell through to repeated waits or unnecessary clarification.

The shared contracts were repaired with regression coverage. Targeted traced reruns produced:

- `fixture__invoice_total_report`: **COMPLETED**, one step;
- `fixture__table_edit`: **COMPLETED**, one step;
- `fixture__dynamic_load`: **COMPLETED**, one step;
- six Google-start workflows: **BLOCKED_CAPTCHA** before planner execution and excluded from completion scoring;
- `first10__04_ai_code_assistant_pricing`: native `open_new_tab` succeeded and reached the product site, exposing a second defect in multi-source target parsing and repeated unverified reports. Those contracts were repaired, but the verification rerun was CAPTCHA-blocked before planning.

Requested-count parsing now preserves multi-source targets expressed as “3 AI code assistant products” and “3 different tools.” Repeated identical unverified reports terminate as `STUCK` after three turns instead of consuming the full task budget.

The frozen baseline remains 16.1% until the complete 38-task suite is rerun under a non-challenged search environment. See [planning-cluster-delta-2026-08-15.md](planning-cluster-delta-2026-08-15.md).

## Paired current baseline — 2026-08-15

The complete frozen suite was rerun in both executor modes on the same code and environment:

- Playwright: **16/22 counted completed (72.7%)**, 9 blocked, 7 skipped, 4 errors, 1 timeout, 1 stuck; 50 raw step traces.
- Synthetic: **14/22 counted completed (63.6%)**, 9 blocked, 7 skipped, 3 errors, 2 failed, 2 timeouts, 1 stuck; 78 raw step traces.
- Dataset: 38 tasks, unchanged SHA-256 `d60e41501d74e4acf502423e112c34119edfaa88e0718685e9895b39f3a5aa51`.
- Structural joint-report gate: passed with zero errors.
- Changed/benchmark/policy regression set: 243 passed.
- Full repository suite: 4,406 passed and 25 failed; residual failures remain explicitly recorded and are not claimed as passing.

The completion percentage is a measured product result, not itself a Phase 0 pass threshold. Phase 0's objective is a trustworthy, reproducible baseline with unambiguous claims. The technical and project-governance gates are now met. The policy review authorizes Phase 1 implementation subject to its mandatory enforcement conditions; it is not a legal/compliance certification or public-deployment approval.

See [paired-baseline-2026-08-15.md](paired-baseline-2026-08-15.md) for the executor comparison, per-task residuals, hashes, and artifact paths.

See [policy-review-2026-08-15.md](policy-review-2026-08-15.md) for the review evidence, approval scope, mandatory Phase 1 conditions, and residual risk.
