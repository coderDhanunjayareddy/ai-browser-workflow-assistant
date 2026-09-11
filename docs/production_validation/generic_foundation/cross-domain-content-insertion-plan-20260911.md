# Cross-domain content-insertion certification plan

**Recorded:** 2026-09-11  
**Status:** IMPLEMENTATION STARTED — no real-service upload pass is claimed yet

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

## External behavior references

- Chrome DevTools Protocol exposes chooser interception through `Page.setInterceptFileChooserDialog` / `Page.fileChooserOpened` and exact file binding through `DOM.setFileInputFiles`.
- Chrome extensions use `chrome.debugger` as the supported transport for CDP commands on a bound tab.
- Official messaging and mail documentation confirms that file selection and final send are separate stages on preview-capable surfaces; the certification intentionally stops before send.

