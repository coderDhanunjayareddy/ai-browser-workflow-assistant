# Cross-domain content-insertion certification plan

**Recorded:** 2026-09-11  
**Status:** CI-1 IMPLEMENTED AND LOCALLY VERIFIED — no real-service upload pass is claimed yet

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
- Each service passes 5/5 fresh runs before the 20-run application-owned upload certification is resumed.
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

## External behavior references

- Chrome DevTools Protocol exposes chooser interception through `Page.setInterceptFileChooserDialog` / `Page.fileChooserOpened` and exact file binding through `DOM.setFileInputFiles`.
- Chrome extensions use `chrome.debugger` as the supported transport for CDP commands on a bound tab.
- Official messaging and mail documentation confirms that file selection and final send are separate stages on preview-capable surfaces; the certification intentionally stops before send.
