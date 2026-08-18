# Day 3 Trusted-Grounding Report

**Date:** 2026-08-18  
**Trusted-grounding implementation:** Complete

**Expanded Day 3 robustness implementation:** Open

**Day 3 live exit:** Not met; the robustness gate and required 20/20 application-side-panel runs are not claimed.

## Delivered

- Made the canonical CDP controller the sole production mutation route for click.
- Enforced ordered grounding: unique stable selector, one exact accessibility identity, then explicitly verified screenshot coordinates.
- Bound screenshot fallback to a fresh screenshot hash, verified flag, viewport point, and compatible hit target.
- Added structured grounding attempts and fallback reasons to adapter traces.
- Added bounded exact post-click verification for WhatsApp chat headers, Gmail thread subjects, Google Docs titles, and Google Drive item headings.
- Extended the canonical contract and backend policy enforcement with the grounding policy.
- Repaired two runtime-launch bottlenecks: an unbounded PowerShell health probe and a false wrapper-PID/server-PID mismatch. Direct health preflight now prevents duplicate startup when Windows listener enumeration is restricted.
- Made explicit safe navigation the application-owned bootstrap path: a workflow may open an `http`/`https` destination from only Chrome New Tab or `about:blank`; other privileged origins remain blocked. The destination URL is preserved in the canonical contract and enforced by both extension and backend policy.
- Prevented a new Analyze submission from inheriting a restored workflow session. New tasks now receive a fresh session/idempotency namespace; Resume alone retains the existing session.
- Removed a development auto-reload parent/worker pair that was silently recreating a `local-dev` backend after the canonical worker stopped. The validation runtime is now one non-reloading process.

The production invariant is documented in [trusted-grounding-and-postconditions.md](../../stabilization/trusted-grounding-and-postconditions.md).

## Automated verification

- Extension TypeScript type-check: passed.
- Production extension build: passed.
- Extension full suite: **170/170 passed**.
- Backend policy/API focused suite: **24/24 passed**.
- Canonical runtime/extension handshake: URL `http://localhost:8000`, server PID `18268`, build `stabilization-20260818T113543Z`, commit `6c60c20`.

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

Two operator-side submissions also exposed pre-dispatch defects without producing a browser mutation: the first reused a restored workflow session, and the second was correctly blocked because New Tab was treated as an unsupported origin. Both root causes are now fixed and regression-covered. The next qualifying run must begin on New Tab and demonstrate that the application opens WhatsApp before it grounds and opens the exact direct chat.

## Expanded robustness checkpoint

Product-intent review showed that an explicit URL in the WhatsApp validation prompt would mask a general navigation gap. Day 3 now requires natural-language destination resolution, compound-objective decomposition, capability/site compatibility checks, ambiguity clarification, bounded semantic recovery, and meaningful terminal responses before the 20/20 run.

This checkpoint is informed by the documented ChatGPT/Codex browser behavior as a reference product: browser navigation and multi-step website interaction, web search, existing-Chrome operation through an extension, shared visible state, and user control. It does not assume or copy undocumented private implementation details.

Acceptance cases are maintained in the main 15-day plan and include YouTube natural-language resolution, Gmail plus music as a compound task, an impossible Gmail-contained playback request, ambiguous RBVRRIT portal discovery, unverifiable destinations, and bounded failure handling.

## Day 4 entry condition

Per the schedule-control rule, Day 4 must begin by attaching the rebuilt unpacked extension to an authenticated, network-enabled validation browser (or by the operator opening its side panel in connected Chrome) and completing the 20 consecutive non-sending application runs. Only then should attachment-preview work begin.
