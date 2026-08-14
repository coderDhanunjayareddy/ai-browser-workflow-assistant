# Phase 0 Playwright Baseline — 2026-08-14

## Run identity

| Field | Value |
|---|---|
| Run ID | `m0-phase0_baseline-1786728413` |
| Suite | `phase0_baseline` |
| Executor | Playwright, headless |
| Frozen tasks | 38 |
| Duration | 466.2 seconds |
| Dataset SHA-256 | `d60e41501d74e4acf502423e112c34119edfaa88e0718685e9895b39f3a5aa51` |
| Manifest errors | 0 |

## Raw outcome

| Outcome | Count |
|---|---:|
| Completed | 5 |
| Failed | 14 |
| Timeout | 8 |
| Stuck | 2 |
| Error | 2 |
| Skipped prerequisites | 7 |
| Counted tasks | 31 |
| Completion rate | 16.1% |
| 95% confidence interval | 7.09%–32.63% |

Failure classification among non-completions: 10 planning, 8 timeout, 6 infrastructure, and 2 unknown.

The completed tasks were the Instagram profile-view observation, login fixture, pagination fixture, modal fixture, and file-download fixture. Authenticated Google, LinkedIn, and Canva tasks plus controlled signup were skipped rather than counted as successes.

## Published evidence

- Machine-readable report: `backend/benchmark/reports/phase0-baseline-20260814.json`
- Human-readable report: `backend/benchmark/reports/phase0-baseline-20260814.md`
- HTML report: `backend/benchmark/reports/phase0-baseline-20260814.html`
- Raw trace root: `backend/benchmark/trace_out/m0-phase0_baseline-1786728413/`
- Trace coverage: 31 executed-task directories, 104 step JSON traces, and 28 HTML viewers. Skipped tasks have no execution trace; zero-step runner errors may not have an HTML viewer.
- Integrity manifest: `backend/benchmark/reports/phase0-manifest-20260814.json`

## Interpretation

The fixture self-test passed 3/3 with no infrastructure failures before this run, and all three smoke fixtures also completed within the full suite. Therefore the 16.1% result is accepted as the first honest product baseline. It is not evidence of production readiness and does not satisfy the Phase 0 exit gate.

The next improvement work should begin with the dominant failure clusters in this order: planning (10), timeout (8), infrastructure (6), then unknown runner errors (2). Synthetic baseline publication and policy/security review remain separate Phase 0 requirements.
