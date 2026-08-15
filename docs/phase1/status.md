# Phase 1 — Unified live safety gate

Status: **implemented and verified on the current live extension execution path**  
Date: 2026-08-15

## What is live

The browser executor has one privileged entry point: `EXECUTE_ACTION` in the extension service worker. The service worker now validates the sender and message, binds the action to the observed tab, checks that the page did not change, and calls `POST /policy/enforce` immediately before the browser mutation. A missing, unreachable, malformed, or denying policy response fails closed.

The backend policy engine owns the decision. The side panel may request authority, but it cannot declare an action allowed. Automatic mode only proceeds on a direct `allow`; it cannot mint a confirmation receipt.

## Authority model

- Confirmation receipts are issued only after a human-side-panel approval.
- Each receipt is bound to one session, normalized origin, action ID, and SHA-256 digest of the exact action arguments.
- Receipts expire after at most 300 seconds and are consumed atomically once.
- Origin grants are bound to one session, exact scheme/host/port, a narrow list of non-consequential action types, and expire after at most 3,600 seconds.
- Origin grants can be revoked and cannot authorize consequential action classes.
- Unknown action types and non-HTTP(S) privileged navigation arguments are rejected.

## Prompt injection and provenance

The planner receives page text as untrusted input. High-confidence instruction override, secret-exfiltration, and policy-bypass patterns stop before planning and return no action. Other instruction-like page content escalates for human review. Every execution request must carry all three of these labels:

- trusted user task;
- untrusted planner proposal;
- untrusted page observation, including detected injection labels.

The final policy engine independently blocks or escalates actions influenced by injection labels; this is enforced again even if an earlier layer missed or ignored the condition.

## Durable audit

Policy evaluations, authority issuance/revocation, receipt consumption, and execution allow/deny events are stored in SQL tables. Audit events record the action digest and decision metadata, not the raw action value, so passwords, tokens, or typed private content are not copied into the policy audit.

Live endpoints:

- `POST /policy/evaluate`
- `POST /policy/confirm`
- `POST /policy/enforce`
- `POST /policy/origin-grants`
- `POST /policy/origin-grants/{grant_id}/revoke`
- `GET /policy/audit/{session_id}`

## Exit-gate evidence

| Gate | Result | Evidence |
|---|---:|---|
| Consequential action cannot bypass the policy gate | Pass | All current Chrome mutation calls are reachable only through the validated service-worker `EXECUTE_ACTION` handler; enforcement is fail-closed immediately before mutation. |
| Critical confirmation recall | 100% | 10/10 representative critical classes required confirmation or handoff. |
| Backend policy/API tests | Pass | 44 focused tests. |
| Extension security tests | Pass | 9 tests, including malformed-message fuzzing and unavailable/malformed policy responses. |
| Existing extension workflow regression tests | Pass | 55 tests. |
| TypeScript contract check | Pass | `tsc --noEmit`. |
| Production extension build | Pass | `vite build`. |

Commands used:

```text
backend/.venv-codex/Scripts/python.exe -m pytest tests/unit/test_phase1_live_policy.py tests/unit/test_phase1_prompt_injection.py tests/unit/test_phase1_policy_api.py tests/unit/test_v3_governance.py tests/unit/test_phase0_policy_taxonomy.py -q
cd extension && npm run test:security
cd extension && npm run test:workflow
cd extension && npm run type-check
cd extension && npm run build
```

## Honest limits

- Prompt-injection detection is deterministic and conservative, but no detector can guarantee recognition of every future attack. The independent execution-time policy and narrow authority artifacts remain mandatory.
- The gate covers the application's current live Chrome execution path identified in Phase 0. Any future executor or privileged message type must be added to this boundary and its tests before being marked live.
- These checks establish the Phase 1 engineering gate; broader adversarial browser evaluation should continue in later phases.
