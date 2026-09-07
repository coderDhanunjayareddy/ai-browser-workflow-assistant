# Foundation Days 7–8 — One Executor and Effect Verifier

**Recorded:** 2026-09-07  
**Status:** PASS for the generic executor/verifier foundation gate  
**Runtime:** `v0.4.0`, commit identity `4e0cc48-dirty`, build `stabilization-20260907T122217Z`, backend PID `28972`, `http://localhost:8000`

This result closes the recovery-plan Days 7–8 infrastructure gate. It does not certify every external website and does not resume the original application-owned upload or consequential-send gates.

## Implemented

- `handleExecuteAction` is the sole production mutation gateway.
- Every supported action selects exactly one canonical strategy before dispatch: navigation, trusted CDP, tab control, wait, rich text, Wave 2, Wave 3, or Wave 4. Unsupported actions fail closed.
- The production gateway no longer imports the legacy executor, executor v2, widget adapter, upload handler, or selector-recovery dispatcher.
- Stable selectors remain first, exact accessibility identity second, and verified screenshot coordinates last.
- Canonical contracts preserve origin, URL, tab, window, frame, exact target identity, typed expected effect, safety class, and idempotency key.
- `verifyActionEffect` is the authoritative success gate. Raw executor success is converted to failure when the typed effect is not observed.
- The side panel may capture a fresh page observation for the next planning turn, but it cannot reinterpret a canonical v1 verification result.
- Automatic retries are limited to safe reversible actions whose typed effects are retryable. Consequential and uncertain dispatches remain non-retriable.
- Exact opened-resource checks now apply only to resource identities such as chats, threads, documents, and files; ordinary named controls are not misclassified as opened resources.
- Live-evidence capture now records bounded canonical adapter traces and durable execution records.

## Automated validation

| Check | Result |
|---|---:|
| Extension TypeScript check | PASS |
| Extension complete test suite | 229/229 passed |
| Backend contracts, capability, grounding, policy, observed-control, semantic-kernel, and integration suites | 161/161 passed |
| Extension production build | PASS |
| Architecture authority-map JSON validation | PASS |

Typed-effect tests cover URL, target state, value, selection, viewport, tab state, page state, and no-mutation outcomes. The suite also verifies no-effect rejection, exact identity preservation, single leaf dispatch, bounded reversible retries, and non-replay of uncertain/consequential operations.

## Live side-panel certification

The final scenario started from `chrome://newtab/`, navigated to an unfamiliar local synthetic origin, selected one enabled exact-name control among randomized order, partial-name, prose-only, hidden, and disabled decoys, and verified the requested terminal state.

| Run | Status | Actions | Attempts | Canonical click path | Terminal evidence | Duration |
|---|---:|---|---:|---|---|---:|
| `GF-D78-FINAL-01` | PASS | `navigate`, `click` | 1 each | `service_worker>policy>canonical_cdp_click` | `fixture_state=continued_exactly_once` | 31.1 s |
| `GF-D78-FINAL-02` | PASS | `navigate`, `click` | 1 each | `service_worker>policy>canonical_cdp_click` | `fixture_state=continued_exactly_once` | 26.3 s |

For both runs:

- Every durable execution used canonical contract schema `1.0`.
- Every typed effect returned `verification.verified=true`.
- The click used trusted CDP input with `stable_selector:selected_unique_exact` grounding.
- The exact selector was preserved and the accessible name was `Continue`.
- There were zero retries, duplicate clicks, uploads, submissions, messages, account changes, or external side effects.

## Failures found and resolved

1. A harness-only reload attempt on a fresh isolated profile closed the extension page and produced `ERR_BLOCKED_BY_CLIENT`. No workflow or page mutation ran. The redundant reload was removed from the fresh-profile invocation.
2. A real side-panel run executed and verified both actions and reached the correct terminal page state, but the task ended as failed because `Verify fixture_state becomes continued_exactly_once` was not recognized as a state clause. The generic state parser now accepts identifier-named state clauses. The new unit regression passed, a focused live regression passed in 29.9 s, and the final two consecutive runs above used the formerly failing wording.

## Evidence

- Machine-readable final results: `docs/production_validation/generic_foundation/days7-8-final-live-evidence.json`
- Side-panel screenshots: `docs/production_validation/live_sidepanel/gf-d78-final-01.png`, `gf-d78-final-02.png`
- Target screenshots: `docs/production_validation/live_sidepanel/gf-d78-final-01-target.png`, `gf-d78-final-02-target.png`
- Canonical authority map: `docs/architecture/generic-authority-map.json`

## Next gate

Proceed to recovery-plan Day 10: generic operation/effect confirmation policy. Original Day 4 upload and Day 5 exactly-once send certification remain paused until Day 10, Days 11–14, and the Day 15 release decision are complete.
