# Cross-domain content-insertion certification plan

**Recorded:** 2026-09-11  
**Status:** CROSS-SURFACE LIVE CERTIFICATION IN PROGRESS — messaging preview 2/2 passed; mail-draft preview pending

## Objective

Certify one provider-neutral content-insertion path across structurally different real web surfaces. A provider adapter may expose observations, but it may not choose the file, destination, confirmation policy, executor, or success result.

## Contract and safety invariants

1. Bind one exact synthetic leaf filename to one immutable file identity: filename, MIME type, positive size, SHA-256, and broker source.
2. Bind that file to one exact browser tab, frame, HTTP(S) origin, document URL, and destination entity.
3. Classify the insertion effect before selection: preview-before-commit, structured draft, editor insertion, immediate upload, or device capture.
4. Require action-time confirmation for file disclosure. Immediate-upload and device-capture effects receive an additional pre-dispatch stop when their effect cannot be proven reversible.
5. Reserve one chooser before trusted input. A stale, consumed, cancelled, or uncertain reservation cannot open a second chooser automatically.
6. Use the single trusted CDP mutation path: observe an exact enabled control, intercept one chooser, bind one broker-approved file with `DOM.setFileInputFiles`, and verify afterward.
7. Success requires independently observed postconditions: exact file metadata, exact document/origin, exact destination entity where applicable, one selected file, accepted state, and visible preview identity. A click or chooser event alone is not success.
8. Never click send, submit, publish, post, share, or upload-confirm controls during the preview-only gate.

## Implementation stages

### CI-1 — Destination and effect binding

- Add exact document URL and non-empty destination identity to every production content-insertion declaration.
- Infer effect from provider-neutral task semantics and observed capability, not application names.
- Include filename, destination, document, kind, and effect in the request/idempotency identity.

### CI-2 — Capability discovery and target grounding

- Support direct file inputs, labelled file inputs, menu-triggered inputs, and transient insertion menus.
- Rank by exact accessible identity, compatibility with requested content kind, enabled/visible state, composer/editor proximity, and accepted MIME types.
- Clarify rather than select when remaining candidates can have different effects.

### CI-3 — Broker and chooser hardening

- Validate the current tab/document again immediately before selection.
- Reject path-shaped names, ambiguous exact matches, stale grants, MIME mismatch, cross-origin drift, frame drift, and second chooser attempts.
- Mark failed or uncertain dispatch non-retriable until a fresh user-approved request is created.

### CI-4 — Cross-surface verification

- Verify one messaging-style preview surface and one structurally different draft/editor or storage-style surface.
- Use only a small synthetic file with a known hash.
- Collect the action contract, runtime trace, screenshot/visible target where available, latency, retries, chooser count, no-effect actions, and duplicate effects.

### CI-5 — Negative and recovery matrix

- Wrong file, wrong MIME, wrong document, wrong origin, ambiguous destination, disabled decoy, stale chooser, delayed preview, restart before selection, and restart after uncertain selection.
- Every terminal path must be meaningful: complete, confirmation required, clarification required, externally blocked, unsupported, or safely failed.

## Exit gate

- Two structurally different authorized real services pass preview-only insertion.
- Live sampling uses two fresh runs on the first surface and one fresh run on a structurally different second surface. Repetition beyond those samples is covered by deterministic automated tests so the product owner is not repeatedly asked to approve the same disclosure.
- Zero sends/submissions, wrong files, wrong destinations, duplicate selections, second choosers, or unverified success claims.
- The original Day 4 20/20 gate remains separate and is not converted to PASS by this cross-domain checkpoint.

## Implementation checkpoint — 2026-09-11

- Production declarations now bind the exact HTTP(S) document URL as well as the destination entity, file identity, content kind, and expected effect.
- The extension rejects a missing/privileged destination URL and revalidates the exact origin, path, query, and required fragment immediately before chooser dispatch and after selection.
- Provider-neutral effect classification distinguishes preview-before-send, structured drafts, editor insertion, immediate upload/storage, and device capture. Unknown `upload`/`store`/`save` semantics take the safer immediate-effect class.
- Content insertion is compiled as `content_transfer.insert`, not an ordinary click. Its generic capability contract carries the requested filename, destination URL, effect, zero retry budget, and confirmation requirement.
- The chooser ledger records the exact destination URL and continues to block a second chooser after selected, cancelled, or uncertain dispatch.
- Approved synthetic artifact: `synthetic-day5.txt`, `text/plain`, 130 bytes, SHA-256 `5009cc5417c8c6b175e13637bff785182c49e8d78f91ed9f07dbdec840c10945`, resolved through `local_downloads_broker_exact_match`.
- The broker now computes the file SHA-256 itself. Post-selection verification compares filename, MIME type, byte size, SHA-256, origin, and exact document URL to that broker result; a mismatch is terminal and non-retriable.
- Verification: 87 focused insertion/orchestrator/broker/capability tests passed; 43 policy and generic capability boundary tests passed; all 249 extension tests passed; TypeScript check and production build passed.
- Canonical runtime rebuilt with the final hash binding as `stabilization-20260911T054933Z`, commit handshake `364eb73-dirty`, PID `5700`. The broker response was rechecked against the synthetic artifact and returned its exact filename, MIME type, 130-byte size, and expected SHA-256.

Still pending: reload the unpacked extension, then run the live action-time confirmation and preview-only matrix on two authorized structurally different services. No live service pass is inferred from local tests.

### Live diagnostic 01

The first real messaging-preview attempt is a safe failing diagnostic, not a pass. It executed one navigation, three bounded waits, one search fill, and one exact destination click. It then asked for destination clarification before opening a chooser. Independent workflow history confirms zero chooser, file-selection, or send events. Root cause: duplicated accessibility sources were concatenated into a false composite composer identity, while requested and displayed identities also differed only by presentation spacing around parentheses.

The verifier now parses each accessibility source independently, deduplicates repeated supporting composer identities, normalizes only presentation-level Unicode/paired-punctuation spacing, and continues to reject conflicting identities. The content-trigger recognizer received the same per-source correction so duplicated `Attach` metadata cannot become `Attach Attach`. Focused provider-neutral messaging/insertion regressions: **89 passed**, including repeated-support acceptance and conflicting-identity rejection.

### Live diagnostic 02

The corrected identity run reached a genuine visible attachment preview for `synthetic-day5.txt` (`TXT`, `130 B`, one selected item) in the exact requested conversation. It is still not counted as a certification pass because the workflow did not terminate: the service worker's verified `destination_url` was omitted by the side-panel evidence serializer. The orchestrator therefore attempted `Add file`; the chooser ledger correctly rejected it as `second_chooser_blocked`, so no second chooser opened and Send remained untouched.

`destination_url` is now preserved as priority evidence from executor result through the analyze request. The serializer regression and complete extension suite pass: **249/249**, TypeScript check passed, and the focused messaging/orchestrator suite passed **80/80**. A clean rerun is still required before any live pass is awarded.

### Messaging-preview live pass 1/2

The first clean rerun passed under session `94d668a1-ac37-4694-b800-f5c93d0f2b20`. It executed exactly five actions—navigate, search fill, exact destination click, insertion-menu click, and one file-selection click—with zero retries, recoveries, planner calls, redundant insertion actions, or send actions. Independent browser inspection observed the exact destination, `synthetic-day5.txt`, `TXT`, `130 B`, and one selected item. The visible `Send 1 selected` control remained untouched. End-to-preview latency was 48.004 seconds.

### Messaging-preview live pass 2/2

The second fresh run passed under session `cdaca279-9636-47fe-a376-5dc9dbd1f1f0`. Independent browser inspection observed the exact destination `Ramu (Nanna)`, the exact preview filename `synthetic-day5.txt`, `TXT`, `130 B`, and exactly one selected item. The visible `Send 1 selected` control remained untouched. The persisted audit contains exactly five approved and five successful executed events—navigate, search fill, exact-destination click, insertion-menu click, and one document/file-selection click—with zero failed executions, retries, recoveries, planner calls, duplicate chooser actions, or send actions. End-to-preview action latency was 40.092 seconds. Messaging-preview certification progress is now **2/2**.

Per the product owner's 2026-09-11 decision, the two independent clean passes complete the live repetition sample for this surface. This is recorded as **2/2 sampled live passes**, not misrepresented as the original 5/5 gate. Further repeatability coverage is automated.

### Mail-draft live diagnostic 01

The first second-surface submission did not create or modify a draft. It began from `chrome://newtab/` with a capability-only instruction that did not name a mail service or account. Destination resolution returned no destination, the semantic layer proposed a refresh wait, and the canonical executor rejected that action because browser-owned origins cannot enter the HTTP(S) mutation contract. Five observed sessions ended at that same pre-navigation boundary with zero draft, recipient, attachment, chooser, or send actions.

The provider-neutral correction now converts a capability-only request on a browser-owned page into a meaningful clarification for the missing website/application and account instead of emitting an invalid wait. No mail provider is selected implicitly. The regression plus destination, semantic-kernel, and orchestrator suites pass **101/101**. The Windows runtime launcher was also hardened against host environments containing both `Path` and `PATH`; the canonical backend is healthy on build `stabilization-20260911T080229Z`, PID `8872`.

### Mail-draft live diagnostic 02

The corrected explicit-destination run navigated successfully but did not create a draft. One trace failed to focus the opened tab because the workspace intentionally omitted its client-side route fragment while the action referenced the full fragment URL. Another planner attempt selected the inbox search field with no subject value. No draft, recipient, attachment, chooser, or send mutation occurred, so this diagnostic is not a pass.

The reusable corrections are now implemented without a provider or origin special case:

- URL tab matching compares scheme, host, effective port, path, and query; a missing SPA fragment may match only when the resulting live tab is unique. Conflicting explicit fragments and multiple same-document tabs fail closed.
- Structured-draft tasks now follow observed semantics deterministically: activate one unique draft-creation control, fill one unique subject field with the exact supplied subject, and only then expose content insertion. Multiple composers or subject fields request clarification instead of guessing.
- A quoted filename is sufficient content identity for an attach instruction; the user is not required to repeat the noun `file` after supplying an exact filename.

Verification after correction: complete extension suite **251/251**, focused backend regression **151/151**, broader provider-neutral workflow regression **174/174**, TypeScript check passed, and the production extension build passed. Canonical runtime: build `stabilization-20260911T095019Z`, commit `dcaf6dd`, PID `7200`. A fresh live mail-draft preview is still required; no second-surface pass is inferred from these automated results.

### Mail-draft live diagnostic 03

The corrected build opened one draft and filled the exact subject successfully, but it did not select a file. Independent browser inspection found the intended draft still open with an empty recipient and body and no attachment preview. The audit contains exactly one navigation, one draft-creation click, one subject fill, and one incorrect click on the unrelated `More labels` control; zero chooser, file-selection, recipient, body, send, or discard actions occurred. This is a safe failure, not a pass.

Root cause: the generic insertion vocabulary accepted bare `More`/`Add` text as sufficient evidence for an insertion-menu trigger. On a large application surface, that allowed an unrelated navigation control to outrank the composer attachment control. The correction removes bare `More` and `Add` as insertion identities and requires attachment/upload/file-specific evidence. The file-upload phase graph also bypasses the research `READ` phase so an interactive composer cannot be routed into page extraction after a failed insertion action. Focused provider-neutral regressions, including unrelated More/Add decoys and structured-draft progression, pass **142/142**. The next validation will resume the already-open draft rather than create a duplicate.

### Mail-draft live diagnostic 04

The attempted restart recovery did not resume session `33d86293-7fb4-424f-a01e-d840c380f000`. A new session, `66d6b5c9-08a0-422e-8b00-7df6750aed31`, was created at 2026-09-11 10:16:38 UTC and repeated navigation, draft creation, and subject fill. Independent browser inspection showed the draft count increase from 2 to 3. The newly visible draft had the exact subject, empty recipient, empty body, and no attachment preview. Its audit contained six events—three approved and three successful executed actions—and zero chooser, file-selection, send, or discard actions. This is a recovery/idempotency failure, not a second-surface pass.

Two provider-neutral corrections now protect restart recovery. First, every completed action durably records its observed tab and window identity; a resumed workflow re-observes the most recent evidenced tab directly instead of whichever browser tab happens to be active. Older ledgers fall back to canonical result `page_context.tab_id` or `opened_tab_id` evidence, and never invent a tab. Second, a failed restored workflow exposes `Resume safely` as its primary control; the same prominent control no longer starts a fresh mission while a recoverable checkpoint is displayed. Starting a new task remains available through Clear and a new submission.

Verification after correction: complete extension suite **253/253**, including new durable-tab selection regressions; TypeScript check passed; production extension build passed. The canonical backend remains PID `21236`, build `stabilization-20260911T101239Z`, commit `dcaf6dd-dirty`; the extension was rebuilt with that exact handshake. A live resume against the current exact-subject draft is still required. No mail-draft insertion pass is inferred from the automated checks.

### Mail-draft live diagnostic 05

The next claimed resume again created a fresh mission (`f0a64a4b-4c92-4368-9ee9-9f9682d96af9`) rather than continuing the durable mission. Its six events repeated navigation, draft creation, and subject fill. Independent accessibility inspection showed `Drafts 4 unread`, the exact subject, empty recipient and body, an available `Attach files` control, no attachment preview, and untouched Send/Discard controls. This is another recovery/idempotency failure and not a pass.

The submission boundary now provides a second, independent guard: submitting an identical interrupted task with verified completed actions reuses the durable session and refreshes from its last verified tab instead of allocating a new session. A deliberately fresh repeat requires clearing the prior workflow first. This protection is task- and provider-neutral. The complete extension suite passes **254/254**, the focused routing suite passes **75/75**, and TypeScript passes. A uniquely identifiable canonical build is now available as `stabilization-20260911T104104Z`, commit `dcaf6dd-dirty`, PID `10728`; the unpacked extension must be reloaded once to activate that build.

### Mail-draft live diagnostic 06

Session `7594c21d-d523-47b5-a278-c204375ce81e` executed one navigation, one draft-creation click, and one exact subject fill, then the execution orchestrator advanced to `REPORT` and rejected a planner `wait` because `REPORT` permits no browser actions. The audit contains six events, all three mutations succeeded, and contains zero chooser, attachment, send, or discard events. This is a safe failure and not a second-surface pass.

Root cause: validation completion tested the broad `interactive task` condition before required artifact effects. Consequently, any verified intermediate mutation—such as subject fill—could complete `VALIDATE` even while the explicit `uploaded_files=1` target remained at zero. Validation now gives declared effect targets precedence: attachment/upload workflows remain in `VALIDATE` until the uploaded-file/preview artifact count is satisfied, and download workflows remain there until completed-download evidence exists. A verified intermediate click or fill is progress only, never completion of a missing artifact objective.

The new regression proves that an exact verified subject fill leaves a compound draft-and-attach workflow in `VALIDATE`, while broker-backed attachment preview metadata advances it to `REPORT`. The focused provider-neutral orchestrator, grounding, and task-language suite passes **134/134**. Canonical runtime and extension handshake: build `stabilization-20260911T110401Z`, commit `cb0bbb6-dirty`, PID `27872`.

## External behavior references

- Chrome DevTools Protocol exposes chooser interception through `Page.setInterceptFileChooserDialog` / `Page.fileChooserOpened` and exact file binding through `DOM.setFileInputFiles`.
- Chrome extensions use `chrome.debugger` as the supported transport for CDP commands on a bound tab.
- Official messaging and mail documentation confirms that file selection and final send are separate stages on preview-capable surfaces; the certification intentionally stops before send.
