# Phase 3 — Durable autonomous loop

Status: **implemented and verified for the live extension workflow path**  
Date: 2026-08-17

## Durable ledger

The extension now checkpoints task state, mission/workspace snapshots, pending approval state, verified execution history, retry counts, and completion state into one versioned ledger in `chrome.storage.local`.

The ledger is updated at workflow transitions and synchronously before browser dispatch. Closing and reopening the side panel, or restarting the extension service worker, restores the same session and verified history.

Obvious credentials and authentication secrets are removed from durable checkpoints, and raw post-action page context is not stored inside execution results.

## Restart and duplicate safety

- Every action receives a stable idempotency key derived from mission/intent identity and its bound tab.
- A successful key returns its stored result and cannot dispatch twice.
- An action reserved before a restart but not durably completed is marked `uncertain`.
- Uncertain actions are never replayed automatically. The UI pauses and offers **Resume safely**, which performs a fresh observation and replanning pass.
- Pending approvals survive restart, but Auto mode does not; the user remains paused at the policy boundary.

## Bounded autonomy

Automatic execution and automatic retry are limited to actions that are both policy-safe and reversible: fill, select, hover, scroll, and wait. Retries are capped at two attempts. Clicks, navigation, uploads, sends, submissions, purchases, deletions, and other consequential or non-reversible actions pause for explicit approval.

Every retry passes through the Phase 1 live policy engine immediately before execution.

## Completion validation

A workflow reaches `completed` only when one of these validators succeeds:

1. the backend returns an SGV-verified report; or
2. the durable mission-result endpoint returns a mission result.

Typing “done” is treated as user input and no longer bypasses completion validation.

## Exit-gate evidence

The controlled restart suite verifies:

- a serialized 12-step workflow restores its verified history and pending action;
- a successful action is idempotent after restoration;
- an in-flight action becomes uncertain and cannot be dispatched again;
- automatic retries stop after two attempts;
- non-reversible and caution/danger actions do not auto-run;
- completion without SGV or a mission result is rejected.

Verification commands:

```text
cd extension && node --test --test-concurrency=1 tests/*.test.cjs
cd extension && npm run type-check
cd extension && npm run build
```

Current verification result: **157 extension tests passed**, TypeScript passed, and the production build passed.

## Live restart check

1. Reload version **0.3.0** from `extension/dist`.
2. Start a multi-step workflow and complete at least one step.
3. Close and reopen the side panel, or reload the extension.
4. The prior task and verified steps should return.
5. If interruption occurred during dispatch, the extension must show the uncertainty warning and **Resume safely** instead of repeating the action.
