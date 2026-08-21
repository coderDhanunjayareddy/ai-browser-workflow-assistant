# Consequential submission broker

Day 5 implements one provider-neutral boundary for external mutations such as send, share, submit, post, and publish. Provider names, destination names, and content identities are runtime data. Core confirmation, idempotency, dispatch, and verification logic does not branch on an application name.

## Contract

`consequential_submission.v1` binds:

- a stable submission ID and operation;
- exact destination entity;
- exact content identity;
- required visible preview;
- delivered-content-and-destination verification mode.

The declaration is immutable inside the canonical action contract, policy digest, one-use confirmation receipt, and durable execution key. Rebinding a receipt or submission ID to different content or a different destination fails closed.

## State machine

1. Observe the exact destination and exact content preview.
2. Display those identities to the user immediately before the final action.
3. Issue and consume one narrow, expiring confirmation receipt.
4. Atomically reserve the submission ID at the mutation boundary.
5. Dispatch trusted input once.
6. Mark the result `delivered` only after exact post-dispatch evidence; otherwise mark it `uncertain`.
7. Never automatically retry a `delivered`, `dispatching`, or `uncertain` submission.

This follows OWASP's significant-transaction-data and final-authorization-gate guidance. It also follows the established idempotency-key pattern of binding one operation identity to one immutable parameter set. Because arbitrary third-party websites do not expose a server idempotency API, the browser broker deliberately uses stricter behavior after an uncertain click: stop and inspect instead of retrying.

## Adapter boundary

Sites may expose stable `data-submission-destination`, `data-content-identity`, and `data-delivery-state` evidence through an adapter. Without those attributes, the verifier uses bounded visible semantic DOM evidence. Adding a provider adapter may improve evidence quality but cannot bypass confirmation, identity binding, the ledger, or delivery verification.

## Terminal outcomes

- `delivered`: exact destination and content effect verified;
- `already_delivered`: duplicate blocked without dispatch;
- `uncertain_prior_dispatch`: no repeat; re-observation/operator inspection required;
- `precondition_failed`: preview or destination changed before dispatch;
- `policy_blocked`: confirmation/receipt/contract requirement not satisfied.
