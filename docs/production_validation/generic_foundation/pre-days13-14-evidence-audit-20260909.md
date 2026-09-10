# Pre–Days 13–14 Evidence Audit

**Recorded:** 2026-09-09  
**Purpose:** Reconcile reports, raw evidence, runtime state, tests, and remaining release gates before continuing cross-domain certification.

## Corrected schedule status

| Milestone | Evidence-backed status | Boundary |
|---|---|---|
| Day 1 runtime control | Passed | One canonical backend URL and visible runtime handshake are active. |
| Day 2 single executor contract | Passed | Approved mutations cross the canonical action contract. |
| Day 3 grounding and click verification | Passed for its stated authenticated exact-target gate | Raw 20-run evidence contains 20 completed runs, exact-target verification, and no send/upload/submit actions. |
| Original Day 4 upload gate | Reopened / pending | Its historical 20/20 run used Playwright `chooser.set_files`; it is controlled integration evidence, not autonomous application binding. |
| Original Day 5 send gate | Pending | The 20-run result is a provider-neutral loopback fixture. It is not 20 real-service sends and performed zero real sends. |
| Generic Days 7–8 executor/verifier | Passed | Two live neutral-surface runs completed through the canonical trusted path. |
| Generic Day 10 confirmation policy | Passed as a synthetic policy matrix | Six consequential classes paused, identity drift failed closed, one confirmation was accepted, and duplicate confirmation was blocked without browser mutation. |
| Generic Days 11–12 adapter isolation | Passed for the recorded checkpoint | The canonical CDP stable-selector trace was verified and provider adapters remained isolated. |
| Generic Days 13–14 cross-domain conformance | In progress | Ten scenario rows currently pass; content insertion, randomized variants, recovery, safety, and structurally different real-service coverage remain. |
| Day 15 release decision | Blocked | Cannot begin until the Days 13–14 matrix and the reopened original Day 4/5 gates are complete. |

## Raw-evidence reconciliation

- Day 3 raw result: 20/20 completed; latency 29.6–43.0 seconds (38.81 seconds average); 20/20 exact target verification; 20/20 stable-selector CDP evidence; zero send, upload, attach, or submit steps; all 40 run and target screenshots exist.
- Generic Days 7–8: 2/2 completed at 31.1 and 26.3 seconds.
- Generic Day 10: all six consequential operation classes passed the policy matrix; no browser mutation was dispatched.
- Generic Days 11–12: one completed 32.1-second run with a verified canonical stable-selector CDP trace.
- Generic Days 13–14: public search, dynamic dialog, public read, authentication intervention, compound form, pagination, delayed collection (2/2), same-origin frame, tab lifecycle, and native download evidence all parse and match the progress report.
- Native download was separately verified in normal Chrome: one server request, one 106-byte file, exact filename, `text/plain`, and SHA-256 `1FC13CB20F6590BD58EFADB4A17E46E0DE8B9ADD42DE56753583BB50870F4EE0`; no open/upload/share/delete action.
- Twenty-five local evidence links across the audited reports resolve; none are missing.

## Regression and infrastructure audit

- Release-critical backend suite: **363 passed** in 29.35 seconds.
- Extension suite: **244 passed**.
- Extension TypeScript check: **passed**.
- Alembic current/head: `20260908_0004`; schema compatibility: **passed**.
- Canonical runtime health at audit start: backend connected at `http://localhost:8000`, build `stabilization-20260909T154057Z`, PID `30840`. After the audited generality correction, the extension and backend were rebuilt together as `stabilization-20260909T165119Z`, commit marker `4e2af40-dirty`, PID `22764`.
- The full backend suite was intentionally stopped at 6% because it contains thousands of tests and was becoming a validation bottleneck. It was **not** completed and must never be reported as passed.
- The focused suite emitted 625 deprecation warnings, primarily `datetime.utcnow()` and Starlette multipart-import warnings. They are tracked technical debt, not hidden failures.

## Generality audit and correction

Production code was searched for named people and example applications. Application names remain where expected in the centralized destination registry and isolated optional adapters; that is configuration/adapter scope, not executor hardcoding. Legacy executors also contain examples but are not imported by the production service worker.

One executable shadow-path defect was found: semantic control ranking assigned special weight to one literal recipient name. It was removed. Role intent now uses generic terms such as contact, friend, recipient, search, find, and chat. Message-composer ranking now depends on whether the proposed value looks like a message body, not on application or recipient names in the whole task. A regression test proves two arbitrary names receive identical scores.

## Content-insertion truth boundary

The old real-browser fixture test calls Playwright `set_input_files`, and the old Day 4 20-run driver called `chooser.set_files`. Those tests validate the page preview and safety stop but do not certify application-owned local-file binding.

The current production path is distinct: exact leaf filename extraction, exact top-level Downloads resolution, trusted service-worker-only absolute path handling, one chooser reservation, CDP `Page.fileChooserOpened` interception, `DOM.setFileInputFiles`, exact-origin verification, and visible filename preview verification. The next live gate must run without `--legacy-harness-file-selection`; otherwise it cannot pass certification.

## Remaining Days 13–14 gates

1. Extend the passed neutral production-owned content-insertion checkpoint to randomized/recovery variants and structurally different authorized real services. The first production-owned run passed in 47.9 seconds with exact `synthetic-day5.txt`, `text/plain`, 130-byte preview evidence and commit count `0`; no harness-side file selection was enabled.
2. Unseen/randomized DOM variants for each mutation family.
3. Restart/resume and stale-target variants with duplicate-effect accounting. **Completed on the generic fixture path:** the stale-target run produced one effect with no retry, and the browser-restart run restored one checkpoint across a changed tab ID using exact document identity, then committed one resume record. Real-service breadth remains part of the Days 13–14 gate.
4. Prompt-injection, cross-origin leakage, account-confusion, and privileged-URL safety cases.
5. Two structurally different real services for each safe, authorized capability.

## Work started after the audit

- Production-owned neutral content insertion passed in 47.9 seconds with exact broker/CDP evidence and zero commit effects.
- Prompt injection stopped before any page mutation and left its mutation counter at zero.
- Cross-origin frame isolation held. A discovered user-facing fallback defect was corrected and the rerun produced a precise isolation/human-resume outcome with no child content exposure or click.
- Duplicate exact controls across two account sections produced a clarification and no account selection.
- A discovered privileged-URL fallback defect was corrected. The rerun rejected `chrome://settings` on New Tab with zero actions and no web-search substitute.
- Randomized production-owned insertion passed 3/3 with a different generated valid selector on every load and a disabled file-input decoy first in DOM order. All three runs selected the exact broker-bound file once, verified the same filename/MIME/size preview, and left commit count `0`.

This audit does not convert controlled evidence into a release pass. Original Day 4 and Day 5 remain pending until their stated application-owned and real-service gates are satisfied.
