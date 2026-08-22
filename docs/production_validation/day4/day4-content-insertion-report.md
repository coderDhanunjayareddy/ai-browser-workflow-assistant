# Day 4 Generic Content-Insertion and Upload Broker

Date: 2026-08-21  
Frozen runtime: `v0.4.0` / commit `68a9366` / build `stabilization-20260821T095255Z` / PID `10064`  
Canonical backend: `http://localhost:8000`

## Result

Status corrected 2026-08-22: **controlled integration gate passed; production application-only live gate pending**.

Latest corrective runtime prepared 2026-08-22: `v0.4.0` / workspace `6d60a58-dirty` / build `stabilization-20260822T060706Z` / PID `14196`.

The production extension now preserves the exact leaf filename from the user task, resolves only one completed exact-name entry from Chrome's Downloads registry, keeps the resulting absolute local path at the trusted service-worker/CDP boundary (never in planner input or canonical action evidence), arms `Page.fileChooserOpened` before the immutable click, and binds the file exactly once with `DOM.setFileInputFiles`. Missing, ambiguous, incomplete, or path-shaped names fail before a chooser reservation or page mutation. The validation driver defaults to application-owned binding; Playwright `set_files` is available only behind the explicitly labelled `--legacy-harness-file-selection` diagnostic flag.

Automated evidence for this correction: extension type-check passed, extension suite 209/209 passed, focused backend orchestration/broker/policy suite 61/61 passed, production build passed. The application-only live preview proof is still pending because the rebuilt unpacked extension must be reloaded through Chrome's privileged extension-management page; connected browser automation is policy-blocked from opening that URL. No preview or send is claimed for this build yet.

After the owner reloaded the extension, two independent runner probes were attempted. The bundled Chromium profile loaded the matching panel/worker/backend build but Windows returned `ERR_NETWORK_ACCESS_DENIED` for the destination before any application action. Branded Chrome had network access but rejected command-line loading of the unpacked extension (`ERR_BLOCKED_BY_CLIENT` for its extension page). The actual user Chrome extension remained green, but Chrome's connected tab-control API does not expose side-panel DOM. These are externally blocked setup probes, not broker passes or failures. Both produced zero file selections and zero sends. The exact no-send task was copied to the user's clipboard for the single required side-panel submission.

The original report called the 20-run result a completed live gate. A later source audit found that `backend/scripts/run_live_sidepanel_validation.py` registered a Playwright `filechooser` handler and called `chooser.set_files(...)` with the approved fixture. The evidence proves the side panel, browser page, preview verifier, and safety stop worked together, but it does not prove the production extension can independently resolve, bind, and select the named local file. The mandatory gate is reopened until the same run passes with harness-side chooser injection disabled.

The production design is a generic content-insertion broker, not a provider-specific attachment script. It models documents, images, video, audio, device capture, contacts, polls, events, stickers, GIFs, and emoji as typed content kinds with declared effects. The live certification uses one preview-capable messaging adapter as the representative browser surface.

## Harness-assisted live integration result

The certification prompt began from `chrome://newtab/` on every run and contained a natural-language destination, exact entity, exact synthetic filename, preview objective, and explicit no-send boundary.

| Check | Result |
|---|---:|
| Consecutive harness-assisted runs | 20/20 completed |
| Verified actions per run | 5/5 |
| Exact file chooser selections | 20/20 |
| Exact attachment previews | 20/20 |
| Files selected per run | exactly 1 |
| Send actions | 0 |
| Messages/files sent | 0 |
| Retry markers | 0 |
| Duplicate or second choosers | 0 |
| Wrong file bindings | 0 |
| Target screenshots retained | 20/20 |

These figures must not be presented as autonomous application capability. The external validation driver performed the file selection.

Latency was 44.3 seconds minimum, 61.91 seconds average, 73.9 seconds p95, and 74.2 seconds maximum. This does not block the Day 4 correctness gate, but it remains an explicit performance-hardening item before release.

## Certified synthetic binding

- Filename: `synthetic-day4.txt`
- MIME: `text/plain`
- Size: 145 bytes
- SHA-256: `28eb3d4781844dcd2ed035b817ae0ddec805f7dcc73cad649d5c61e106557bb6`
- Content source: repository-owned synthetic fixture only

## Controlled coverage

The controlled browser fixture and policy tests cover:

- `preview_then_send` local-file selection with a separate untouched Send control;
- `selection_sends_immediately`, which requires confirmation before catalog selection;
- `inserts_into_composer` for editable catalog content;
- `structured_draft` for poll/event-style content;
- `device_capture`, which requires permission and confirmation;
- stale, cross-origin, cross-entity, mismatched, uncertain, and second-chooser rejection;
- one-use idempotency and exact binding metadata.

## Root causes found and fixed during live certification

1. A recipient parser consumed the next positive objective sentence. Sentence-boundary parsing now preserves exact entity identity.
2. A broad content-kind matcher selected unrelated global media navigation. Generic insertion-menu triggers now outrank content-kind navigation until the menu is open.
3. A control label was treated as a newly opened resource identity. Exact resource verification and insertion-effect verification are now separate contracts.
4. The page removed/replaced the file input after selection. Selection evidence is now armed before trusted input and survives DOM replacement.
5. Preview inspection exceeded the side-panel action timeout. Its bounded window is now shorter than the action budget.
6. Verbose adapter diagnostics pushed broker evidence beyond the 30-key request schema and caused HTTP 422. Essential identity/safety evidence is now prioritized and the envelope is deterministically capped.
7. The harness interpreted the word `approved` as an approval prompt. Approval detection now requires an explicit approval phrase or control.
8. The production executor had no file-identity-to-local-path bridge; file choice therefore depended on the test harness. Exact filename extraction, Downloads-registry binding, atomic chooser interception, and exact CDP file assignment now form one application-owned path. Traversal-shaped names, no match, multiple distinct matches, and incomplete metadata stop before the chooser opens.

All failures stopped safely. No failed probe sent a message or produced a duplicate chooser side effect.

## Verification commands and results

- Backend focused broker/grounding/policy suite: 53 passed.
- Backend harness/grounding regression suite: 28 passed.
- Extension full suite after broker/verifier work: 195 passed.
- Extension workflow-routing and evidence-bound suite: 60 passed.
- Extension TypeScript type-check: passed.
- Controlled real-browser insertion-effect fixture: passed.

## Evidence

- [20-run raw result](../live_sidepanel/day4-cert-20-run.json)
- [Final target screenshot](../live_sidepanel/day4-cert-20-target.png)
- [Synthetic fixture](fixtures/synthetic-day4.txt)
- [Generic broker architecture](../../stabilization/content-insertion-broker.md)

The final screenshot shows the exact filename in the removable preview while the separate send control remains visible and untouched.
