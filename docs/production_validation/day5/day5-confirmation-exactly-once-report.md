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
- Extension unit/security/workflow suite: 208/208 passed.
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
7. The corrected safe stop exposed a clarification loop: answers were retained only in supplemental planner context while the deterministic destination resolver continued to read the original task entity. Clarification answers now produce an authoritative typed overlay in the effective durable task, and same-URL navigation continuations are rejected before execution. The current extension suite passes all 208 tests, including destination replacement and same-URL loop regressions.
8. Three consecutive no-send runs exposed ambiguous result grounding. Direct inspection of the real accessibility tree established the final root cause: there are two exact `Rahul` identities, one under the `Chats` result group and another under `Messages`; the second is not `Rahul Computers` as initially inferred from the screenshot. The planner selected `span[title="Rahul"]`, which matched both exact identities, and the trusted-input identity check correctly stopped without dispatch each time. The final correction binds the objective type to the nearest evidence-backed result group: an `open chat` objective selects an exact identity only under the matching `Chats` group, while a message-search objective can select `Messages`. It does not choose the first result, prefix matches remain ineligible, and equal-scored destinations still fail closed. A read-only proof against the live DOM produced two candidates with section affinity `Chats=1` and `Messages=0`. No chat click, attachment, or send occurred in any failed run. Backend targeted tests pass 82/82, the CDP suite passes 12/12, and the complete extension suite passes 208/208 after the final correction.
9. The next real run verified the exact `Rahul` chat and opened only the attachment menu, but then paused on a typed 500 ms `WAIT` whose description mentioned an upload control. Policy had classified risk from description keywords without first honoring the typed no-mutation action. The correction treats a `WAIT` with no content-insertion or submission contract as observational; a malformed `WAIT` carrying a mutation contract still enters the normal confirmation path. The visible `synthetic-day5.txt` was not produced by this run: its 6:45 PM message timestamp predates the 6:49 PM workflow start, and the trace records only `button[aria-label="Attach"]` with no chooser selection, upload, or send. Policy tests pass 31/31 after the correction.
10. The following real run passed destination opening and the observational wait, then selected `button[aria-label="Attach"]` a second time instead of advancing to the newly exposed specific content control. The trace showed the same selector in steps 4 and 6. Two state-progression defects caused this: verified CDP click messages were not recognized by the deterministic prior-step success classifier, and the fallback search still considered selectors already used successfully. The correction recognizes verified CDP dispatch, removes completed selectors before selecting the next insertion control, and maps a generic local file to a document-capable control. The new regression proves that a completed `Attach` trigger advances to `Document` with `select_bound_content` and native-chooser semantics. No chooser selection, upload, or send occurred in the failed run. The expanded orchestrator/policy suite passes 135/135.

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
- Latest execution-boundary corrective runtime: `v0.4.0`, workspace `1b71b2b-dirty`, build `stabilization-20260821T125509Z`, PID `12252`.
- Latest live-DOM result-group runtime: `v0.4.0`, workspace `1b71b2b-dirty`, build `stabilization-20260821T130359Z`, PID `27932`.
- Latest typed-policy runtime: `v0.4.0`, workspace `1b71b2b-dirty`, build `stabilization-20260821T132456Z`, PID `29632`.
- Latest insertion-progression runtime: `v0.4.0`, workspace `1b71b2b-dirty`, build `stabilization-20260821T134327Z`, PID `3412`.

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
