# Extension E2E content-insertion checkpoint — 2026-09-11

## Scope

This checkpoint validates a provider-neutral draft lifecycle through the built MV3 extension and its real side-panel workflow:

1. create one synthetic draft;
2. fill one exact synthetic subject;
3. bind and select one explicitly approved synthetic Downloads file;
4. verify the exact visible attachment preview;
5. never send, submit, or discard;
6. restart the isolated Chromium profile and verify that no effect is duplicated.

The harness does not inject the selected file. File resolution and chooser handling remain owned by the extension service worker and local-file broker.

## Implemented

- Added the deterministic `/draft-content-insertion` fixture with independent persisted counters for draft creation, file selection, submission, and discard.
- Added `backend/scripts/run_extension_content_insertion_certification.py`, which loads `extension/dist` into an isolated persistent Chromium context, operates the actual side-panel UI, captures a Playwright trace and screenshots, restarts the profile, and independently reads the target state.
- Preserved a completed control's grounded accessibility identity and semantic kind in the bounded prior-step evidence.
- Updated the provider-neutral planner so an already verified control cannot become a stale required objective merely because it disappeared after use.
- Corrected a harness race in which a verified final report arriving at the timeout boundary was labeled `timeout`.

## Latest executed evidence

Machine-readable run: `extension_e2e/draft-preview-1789125912873.json`

Observed before restart and again after restart:

- `fixture_state=draft_preview_ready_exactly_once`
- draft creations: `1`
- file selections: `1`
- exact subject: `Synthetic cross-domain attachment preview`
- exact preview identity: `synthetic-day5.txt`
- submissions: `0`
- discards: `0`

The extension displayed `✓ Done — 3 of 3 steps succeeded` and reported that the exact broker-bound preview was verified and nothing was sent. Each durable mutation had one attempt. The saved run's top-level status is `failed` only because the first harness version classified that final report after its last timeout poll. That classifier is now fixed and covered by a regression test.

## Verification

- Focused backend and harness tests after the fixes: `134 passed`.
- Full extension tests: `254 passed`.
- Extension TypeScript check: passed.
- Extension production build: passed.
- Canonical runtime: `v0.4.0`, commit `fd5e1f6-dirty`, build `stabilization-20260911T112454Z`, PID `2716`.

## Honest remaining gate

A clean post-classifier headed rerun is still required before this checkpoint is called fully certified. The attempted rerun was rejected before Chromium launched because the workspace had no execution credits. No workaround was used and no clean pass is claimed.

No real Gmail draft, recipient, body, attachment, or send action was created by this checkpoint.
