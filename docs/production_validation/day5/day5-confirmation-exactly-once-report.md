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
- Extension unit/security/workflow suite: 206/206 passed.
- Backend policy/orchestrator tests: 52/52 passed.
- Controlled real-browser fixture: 21/21 tests passed (one no-send preview test plus twenty exactly-once runs).
- Production extension build: passed.

## Root causes found and corrected

1. The earlier UI asked for generic approval but did not display significant destination/content data. The action card now displays both identities and uses a `Confirm & <operation>` control.
2. The durable workflow ledger prevented normal click retries but did not bind one generic external mutation to destination and content. The new submission contract and ledger do.
3. A successful click could be followed by an unverifiable result and later replanning. The mutation-boundary state now becomes `uncertain`, which is non-retriable.
4. Verified delivery lacked a deterministic terminal report, allowing possible redispatch planning. Verified delivery now terminates the objective.
5. Concurrent execution messages could race a storage get/set pair. Submission reservation is serialized, and a 20-way concurrency test permits exactly one reservation.
6. The first real-service staging attempt exposed a safety-critical false grounding: the requested self-chat handle was present in the contact-search field, and that query value was incorrectly treated as evidence that an exact result existed. The synthesized row selector was not present in the observation, so its canonical contract carried no exact name; a related message-search result opened instead. The subsequent upload attempt timed out with no file selection, and nothing was sent. The correction removes search-query-as-result evidence, dispatches only selectors present in the observation, stops with clarification when an exact result is absent, and requires trusted exact-destination evidence before any content insertion or submission action.
7. The corrected safe stop exposed a clarification loop: answers were retained only in supplemental planner context while the deterministic destination resolver continued to read the original task entity. Clarification answers now produce an authoritative typed overlay in the effective durable task, and same-URL navigation continuations are rejected before execution. The current extension suite passes all 206 tests, including destination replacement and same-URL loop regressions.
8. The next no-send run exposed ambiguous fragment grounding: the requested name `Rahul` appeared both as an exact chat row and as a highlighted substring inside `Rahul Computers`. The planner selected `span[title="Rahul"]`, which matched two elements, and the trusted-input identity check correctly stopped after observing `Chats` instead of the requested identity. The correction ranks the actionable result row whose accessible label begins with the exact identity and result metadata, preserves that immutable identity through observation binding, and permits a row selector only when it contains one unique exact-identity descendant. No click, attachment, or send occurred in the failed run. Backend targeted tests pass 82/82 and the complete extension suite passes 206/206 after the correction.

## First real-service staging failure and containment

- Requested destination: account-owned self-chat `@dhanunjaya_somireddy`.
- Incorrectly opened destination: a phone-number conversation that did not match the request.
- Attachment selected: no.
- File chooser evidence: no selection within the bounded 30-second window.
- Send attempted: no.
- Duplicate effect: no.
- User-facing success claim: no; the workflow stopped safely at content insertion.
- Regression coverage after correction: 80/80 destination-resolution, observed-control, and orchestrator tests passed, including search-handle ambiguity and wrong-open-destination mutation blocking.
- Corrected canonical runtime: `v0.4.0`, commit `13d4100`, build `stabilization-20260821T120159Z`, PID `19644`.
- Latest exact-row corrective runtime: `v0.4.0`, workspace `13d4100-dirty`, build `stabilization-20260821T124225Z`, PID `21000`. The `-dirty` marker is intentional so an uncommitted validation build cannot be mistaken for pristine Git commit `13d4100`.

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
