# Day 1 Baseline and Runtime-Control Report

**Date:** 2026-08-18  
**Decision:** Day 1 exit gate passed; all four MVP workflows have a reproducible, evidence-backed first-failure classification. No workflow is release-ready.

## Frozen scope and canonical runtime

- The exact pilot scope is frozen in [mvp-scope-freeze.md](../../stabilization/mvp-scope-freeze.md).
- The one authoritative execution path is published in [canonical-runtime-map.md](../../stabilization/canonical-runtime-map.md).
- Canonical backend URL: `http://localhost:8000`.
- Backend process: PID `21444`; `netstat` showed no listener on validation ports `8001`-`8003`.
- Runtime identity: app `0.4.0`, commit `751bca4`, build `stabilization-20260818T095851Z`.
- `/health` reported `status=ok`, `db=connected`, the canonical URL, and PID `21444`.
- The side panel visibly reported the same identity as `Runtime OK` before counted side-panel runs.

The guarded launcher is [start-stabilization-runtime.ps1](../../../scripts/start-stabilization-runtime.ps1). The machine-readable runtime receipt is [runtime-latest.json](runtime/runtime-latest.json).

## Baseline matrix

| Workflow | Result | Duration | First failing step | Failure class | External side effect |
|---|---:|---:|---|---|---|
| WhatsApp | Timeout | 129.5 s | Click the exact `Teja Spc` search result | Grounding/execution mismatch: the exact target was broadened to a generic `whatsapp` control; verification returned `no_effect`, recovery repeated no progress, and the convergence guard stopped the loop | None; no attachment or send attempted |
| Gmail | Failed | 71.3 s | Navigate from the public Gmail product page to the authenticated inbox | Navigation ownership/verification: proposed `mail.google.com` navigation produced `no_effect`; recovery repeatedly focused the unchanged public Workspace page | None; no draft created and no email sent |
| Google Drive | Failed | 0.0 s workflow time | Harness bootstrap navigation to Drive | Environment/browser network boundary: Chromium returned `ERR_NETWORK_ACCESS_DENIED` before the side panel workflow began | None; no item created, renamed, shared, or deleted |
| Google Docs | Failed | 0.0 s workflow time | Harness bootstrap navigation to Docs | Same environment/browser network boundary as Drive | None; no document created, edited, shared, or deleted |

## Root-cause groups

1. **Exact-target identity is lost before trusted mutation.** WhatsApp proves that extracting the correct visible name is insufficient: the dispatched/recovered control is generic and produces a verified no-effect. Day 2 must preserve exact target identity through one executor contract.
2. **Navigation is not bound to an observable postcondition.** Gmail remained on the marketing page after a navigation proposal, then the recovery policy focused that same page. Navigation must verify origin and authenticated application state before advancing or retrying.
3. **The live validation browser has an external network-permission boundary.** Chromium defines `ERR_NETWORK_ACCESS_DENIED` as network permission being denied, most commonly by a firewall. This is distinct from DNS, authentication, selector, or application failure. Drive and Docs therefore cannot yet be used to judge their workflow implementation.
4. **Backend startup validation is a bottleneck.** Startup schema validation emitted seven incompatibilities and delayed readiness beyond the original 15-second launcher allowance. The launcher now allows up to 60 seconds and reuses only an identity-verified process, but the schema validation itself remains a performance/root-cause item.

The harness now catches bootstrap navigation failures and emits a structured failed-run record plus screenshot instead of terminating with an unclassified traceback. Playwright requires a persistent context for extension testing and documents that the same user-data directory cannot be used by multiple browser instances; profile ownership must remain exclusive during future runs. See the [Playwright persistent-context documentation](https://playwright.dev/python/docs/api/class-browsertype#browser-type-launch-persistent-context) and Chromium's [network error definition](https://chromium.googlesource.com/chromium/src/+/ce688aeeccd445f779dac42ff711f08b9314c9f8/net/base/net_error_list.h).

## Evidence

- WhatsApp: [run JSON](baselines/whatsapp.json), [side-panel screenshot](../live_sidepanel/day1-whatsapp-baseline.png), [target screenshot](../live_sidepanel/day1-whatsapp-baseline-target.png)
- Gmail: [run JSON](baselines/gmail.json), [side-panel screenshot](../live_sidepanel/day1-gmail-baseline.png), [target screenshot](../live_sidepanel/day1-gmail-baseline-target.png)
- Drive: [run JSON](baselines/drive.json), [bootstrap screenshot](../live_sidepanel/day1-drive-baseline-bootstrap-failed.png)
- Docs: [run JSON](baselines/docs.json), [bootstrap screenshot](../live_sidepanel/day1-docs-baseline-bootstrap-failed.png)
- Backend startup: [stderr log](runtime/stabilization-20260818T095851Z.stderr.log)

## Verification performed

- Backend runtime-handshake tests: `2 passed`.
- Extension type-check: passed.
- Extension test suite: `160 passed`.
- Validation-harness Python compilation: passed.
- PowerShell launcher parser validation: passed.
- Canonical runtime health and database connection: passed.
- Listener invariant for ports `8000`-`8003`: passed, with one listener on `8000` only.

## Day 2 entry priorities

1. Define one typed executor contract that preserves exact target, origin, tab/frame, expected effect, safety class, and idempotency key.
2. Disable recovery paths that broaden an exact target or repeat a verified no-effect.
3. Make navigation completion require the intended origin plus an authenticated application-state signal.
4. Isolate and repair the validation browser's Windows network permission/profile ownership issue, then rerun Drive and Docs before product-specific changes.
5. Move or cache expensive startup schema validation so readiness is not blocked by the complete diagnostic pass.

