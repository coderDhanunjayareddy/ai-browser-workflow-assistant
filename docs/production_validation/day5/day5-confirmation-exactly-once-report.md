# Day 5 confirmation and exactly-once report

Date: 2026-08-21

Status: **controlled gate passed; real-service release gate pending**.

## Implemented

- Generic `consequential_submission.v1` contract for send/share/submit/post/publish.
- Confirmation UI shows exact operation, destination, and content immediately before approval.
- Backend issues a narrow, expiring, single-use confirmation receipt bound to the complete action digest.
- A mutation-boundary ledger atomically reserves one submission ID before trusted input.
- Delivered, in-flight, and uncertain submissions are never automatically repeated.
- Post-dispatch verification requires the exact destination and content effect.
- Verified delivery produces a terminal report and cannot re-enter the dispatch loop.
- The implementation contains no provider, recipient, or filename branch in the generic broker.

## Controlled 20-run result

The loopback provider-neutral fixture used the 130-byte synthetic file `synthetic-day5.txt` (SHA-256 `5009CC5417C8C6B175E13637BFF785182C49E8D78F91ED9F07DBDEC840C10945`) and destination `Synthetic Recipient`.

- Isolated runs: 20/20 passed.
- Exact destination observed: 20/20.
- Exact preview identity observed: 20/20.
- First dispatch produced one delivered item: 20/20.
- Deliberate second activation produced an additional effect: 0/20.
- Wrong destinations: 0.
- Duplicate effects: 0.
- Framework-reported call latency: 1.54s minimum, 1.684s average, 1.84s p95, 1.96s maximum.

Raw summary: [day5-controlled-20-run.json](../live_sidepanel/day5-controlled-20-run.json).

## Automated verification

- Extension TypeScript type-check: passed.
- Extension unit/security/workflow suite: 203/203 passed.
- Backend policy/orchestrator tests: 52/52 passed.
- Controlled real-browser fixture: 21/21 tests passed (one no-send preview test plus twenty exactly-once runs).
- Production extension build: passed.

## Root causes found and corrected

1. The earlier UI asked for generic approval but did not display significant destination/content data. The action card now displays both identities and uses a `Confirm & <operation>` control.
2. The durable workflow ledger prevented normal click retries but did not bind one generic external mutation to destination and content. The new submission contract and ledger do.
3. A successful click could be followed by an unverifiable result and later replanning. The mutation-boundary state now becomes `uncertain`, which is non-retriable.
4. Verified delivery lacked a deterministic terminal report, allowing possible redispatch planning. Verified delivery now terminates the objective.
5. Concurrent execution messages could race a storage get/set pair. Submission reservation is serialized, and a 20-way concurrency test permits exactly one reservation.

## External design cross-check

- OWASP recommends showing significant transaction data to the user, enforcing authorization in sequence, binding the final authorization gate to execution, and using credentials unique to one operation: [Transaction Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transaction_Authorization_Cheat_Sheet.html).
- Stripe documents binding one idempotency key to one immutable parameter set and returning/storing the first result so the operation is not duplicated: [Idempotent requests](https://docs.stripe.com/api/idempotent_requests).

## Remaining mandatory release work

The Day 5 exit criterion is **not yet passed**. No real message or attachment was sent in this engineering run. The required 20 consecutive real-service sends still need:

1. a user-opened certification extension tab in the connected browser profile (privileged extension URLs cannot be opened by browser automation);
2. an explicitly identified consenting test contact or self-chat;
3. an immediate, scoped confirmation for the exact synthetic file and defined 20-send test;
4. retained screenshots/traces proving exact delivered attachment, destination, and zero duplicates for every run.

The browser-control connection was restored on recheck, but the connected profile exposed no user-opened tabs and browser safety correctly blocked automation from opening the privileged `chrome-extension://` page. A user must open the compiled certification extension tab once; this setup requirement is not a passed product result.
