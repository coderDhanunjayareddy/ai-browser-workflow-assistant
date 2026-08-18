# Day 3 Trusted-Grounding Report

**Date:** 2026-08-18  
**Engineering implementation:** Complete  
**Day 3 live exit:** Not met; the required 20/20 application-side-panel runs are not claimed.

## Delivered

- Made the canonical CDP controller the sole production mutation route for click.
- Enforced ordered grounding: unique stable selector, one exact accessibility identity, then explicitly verified screenshot coordinates.
- Bound screenshot fallback to a fresh screenshot hash, verified flag, viewport point, and compatible hit target.
- Added structured grounding attempts and fallback reasons to adapter traces.
- Added bounded exact post-click verification for WhatsApp chat headers, Gmail thread subjects, Google Docs titles, and Google Drive item headings.
- Extended the canonical contract and backend policy enforcement with the grounding policy.
- Repaired two runtime-launch bottlenecks: an unbounded PowerShell health probe and a false wrapper-PID/server-PID mismatch. Direct health preflight now prevents duplicate startup when Windows listener enumeration is restricted.

The production invariant is documented in [trusted-grounding-and-postconditions.md](../../stabilization/trusted-grounding-and-postconditions.md).

## Automated verification

- Extension TypeScript type-check: passed.
- Production extension build: passed.
- Extension full suite: **168/168 passed**.
- Backend policy/API/runtime-handshake suite: **26/26 passed**.
- Canonical runtime: URL `http://localhost:8000`, server PID `26336`, build `stabilization-20260818T105438Z`, commit `751bca4`.

## Live WhatsApp findings

The authenticated Chrome session loaded WhatsApp and exposed the exact direct chat plus two group-reference occurrences of the same text.

| Observation | Result | Root cause / disposition |
|---|---|---|
| Exact direct-chat row click followed by exact header/composer check | Passed in live Chrome | Accessible row grounding distinguished the direct chat; exact header and `Type a message to Teja Spc` composer were visible. |
| Five reload-based repetitions | Failed before click | WhatsApp remained in encrypted message restoration longer than the original ready-state deadline; no click or send occurred. The UI became ready after about 34 seconds. |
| Ten accessibility-only search-control reacquisitions | Failed before click | WhatsApp removes the search textbox's accessible name after it contains a query. This supports stable-selector-first grounding for the control. |
| Plain exact-text click after another chat was selected | No effect / wrong occurrence rejected by postcondition | `Teja Spc` also appeared inside group-reference text. Anchoring to the chat row fixed the ambiguity. |
| Broad diagnostic contenteditable selector | Recovered, no send | It selected the message composer and created the unsent draft `BCA Prathiksha`. The draft was immediately cleared with Select All + Backspace; the UI returned to an empty composer and Voice message control. Nothing was sent. This selector is not allowed by the production exact-identity click contract. |

Live side-effect totals: messages sent **0**; files attached **0**; duplicate effects **0**; recovered unsent drafts **1**.

## Why the 20/20 gate is still open

The built extension can be loaded by the isolated Playwright profile, but that browser is blocked before WhatsApp navigation with `ERR_NETWORK_ACCESS_DENIED`. The authenticated Chrome session has working network access, but automation is correctly blocked from opening `chrome-extension://` side-panel pages. Bypassing that privileged-URL boundary was not attempted.

Therefore the live checks proved the website's target ambiguity, delayed readiness, exact row grounding, and exact header postcondition, but they did not prove 20 consecutive dispatches through the rebuilt application side panel. Controlled/unit results are intentionally not counted as live passes.

## Day 4 entry condition

Per the schedule-control rule, Day 4 must begin by attaching the rebuilt unpacked extension to an authenticated, network-enabled validation browser (or by the operator opening its side panel in connected Chrome) and completing the 20 consecutive non-sending application runs. Only then should attachment-preview work begin.

