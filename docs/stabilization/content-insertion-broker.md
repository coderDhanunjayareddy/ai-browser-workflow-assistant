# Generic Content-Insertion Broker

## Purpose

Day 4 implements one reusable capability for inserting user-approved content into an observed destination. Application names, recipient names, file paths, and content labels are runtime data. Core planning and execution do not branch on provider names.

The representative live attachment-preview gate proves one adapter. It does not limit the architecture to that provider.

## Typed content kinds

| Class | Initial kinds | Source |
|---|---|---|
| Local binary | document, image, video, audio, generic local file | Explicit user file selection |
| Device capture | camera photo/video, microphone audio | Scoped browser/device permission plus confirmation |
| Account data | contact | Scoped account permission plus confirmation |
| Structured content | poll, event | Explicit synthetic field values |
| Catalog/composer content | sticker, GIF, emoji | Observed provider catalog or composer control |

Unsupported kinds return `unsupported_capability`; they never fall back to a vaguely related control.

## Insertion effects

Provider adapters must declare the effect before selection:

- `preview_then_send`: selection creates a removable preview; Send remains separate.
- `selection_sends_immediately`: choosing an item is itself consequential. Confirmation is required before selection.
- `inserts_into_composer`: selection adds editable composer content.
- `structured_draft`: selection opens or edits a structured draft such as a poll or event.
- `device_capture`: selection requests hardware/account permission or captures new content; confirmation is required first.

An adapter may expose only a subset of kinds/effects. The broker selects adapters by declared capability and observed evidence, never by provider-name conditionals.

## Immutable request and binding

Every execution carries a `ContentInsertionRequest` containing:

- request ID and idempotency key;
- typed content kind and expected insertion effect;
- exact destination origin and entity identity;
- approved binding ID for file-backed content;
- one-use confirmation receipt when selection itself is consequential.

A local-file `ApprovedContentBinding` contains:

- opaque binding ID, never a planner-supplied path;
- original filename for preview comparison;
- detected MIME/signature, size, and SHA-256;
- exact destination origin and entity identity;
- the request idempotency key;
- approval and expiry timestamps;
- certification synthetic-content marker.

The file's absolute operating-system path is not exposed to the planner or page.

## State machine

`unbound -> approved -> chooser_opened -> selected -> preview_verified -> awaiting_send_confirmation`

Terminal safe states are `cancelled`, `unsupported`, `stale`, `mismatch`, `uncertain`, and `verified_without_send`.

Rules:

1. A reservation permits at most one chooser/capture/catalog selection.
2. Cancellation does not automatically open another chooser.
3. Any uncertain effect blocks retry until inspected or explicitly restarted by the user.
4. Origin, entity, kind, effect, binding ID, idempotency key, filename, MIME/signature, size, and hash are checked at their applicable boundaries.
5. Cross-origin, cross-entity, expired, consumed, or metadata-mismatched bindings fail closed.
6. Preview verification does not authorize Send, Share, Post, Submit, or Publish.
7. A preview is complete only when the exact bound content identity is observed and the consequential control remains untouched.

## Provider adapter contract

An adapter declares:

- supported content kinds;
- insertion effect per kind;
- observed semantic control identity;
- whether a real file input backs the control;
- accepted MIME patterns and multiplicity;
- preview/draft/composer postcondition;
- whether selection, capture, or final submission is consequential.

Generic DOM/accessibility discovery may construct the same declaration dynamically for an unregistered provider. If effect semantics cannot be verified, the broker pauses instead of selecting.

## Resource and bottleneck controls

- Hash file content once per binding and cache only the digest/metadata.
- Do not base64-copy large files through planner or backend payloads.
- Keep binary data in the browser-native file selection path.
- Bound preview polling and DOM evidence size.
- Release expired or consumed binding metadata promptly.
- Never retry a chooser or consequential selection automatically.

## Certification matrix

Controlled fixtures cover every insertion effect, supported/unsupported kind routing, exact binding, MIME wildcard matching, stale/cross-origin/cross-entity rejection, second chooser, uncertain effect, cancellation, and confirmation-before-selection.

The live gate uses one synthetic file, one exact destination entity, one preview-capable messaging surface, and 20 consecutive preview-only runs. Required side-effect totals are: sends 0, duplicate insertions 0, second choosers 0, wrong bindings 0.

