# Day 2 Single-Executor Report

**Date:** 2026-08-18  
**Engineering exit:** Met. One typed and observable privileged dispatch path exists from approval to browser mutation; click has one non-reinterpreting mutation adapter.

## Delivered

- Added `CanonicalActionContract` v1.0 and a deterministic contract builder.
- Bound exact target, origin/full URL, tab/window/frame, resource URL/title, expected effect, safety class, and durable idempotency key.
- Changed `EXECUTE_ACTION` messages to accept the canonical contract instead of a loose action plus separate tab ID.
- Made backend policy requests require and validate the same contract. Confirmation action digests now include it.
- Selected `service worker -> live policy -> canonical CDP click -> verification -> durable ledger` as the production click pipeline.
- Removed the direct service-worker DOM click and blocked generic executor click dispatch.
- Disabled click selector recovery and CDP fallback reinterpretation.
- Made CDP require a unique exact selector and, when available, an exact observed name. It does not fall through to approximate AX/vision grounding for clicks.
- Added contract-linked dispatch evidence to every execution result.

The detailed invariant is published in [single-executor-contract.md](../../stabilization/single-executor-contract.md).

## Verification

- Canonical contract/service-worker focused tests: 14 passed.
- Selector recovery and CDP focused matrix: 29 passed together with contract tests.
- Extension full suite: 165 passed.
- Backend live-policy, API, and runtime-handshake tests: 26 passed.
- Extension TypeScript strict type-check: passed.
- Production extension build: passed.
- Live backend policy probe accepted the contract and returned `low_risk_action` for a no-mutation `wait` action.
- Canonical runtime: backend PID `29756`, URL `http://localhost:8000`, build `stabilization-20260818T103347Z`; the compiled extension contains the same build identity.

## Live browser check

Two safe, non-sending WhatsApp checks were attempted. Neither reached the side panel or executor:

1. bootstrap `domcontentloaded` exceeded the original 15-second harness timeout;
2. after increasing the bounded timeout to 45 seconds, Chromium returned `ERR_QUIC_PROTOCOL_ERROR` for `web.whatsapp.com`.

The harness classified both before any application action. No chat, attachment, or send mutation occurred. This does not count as an end-to-end workflow pass and remains an environment/network prerequisite for Day 3's 20-run click gate.

## Remaining Day 3 work

- Implement exact child-frame CDP targeting rather than the current fail-closed response.
- Produce live 20/20 exact-chat opening evidence once the validation browser network path is stable.
- Add stronger post-click recipient/document identity assertions beyond generic page-state change.
