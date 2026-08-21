# Day 3 Trusted-Grounding Report

**Date:** 2026-08-21
**Trusted-grounding implementation:** Complete

**Expanded Day 3 robustness implementation:** Complete

**Day 3 live exit:** Passed. Scenarios 1–6 have retained live evidence, and a corrected harness completed 20/20 consecutive authenticated application-side-panel runs genuinely starting from Chrome New Tab. The earlier pre-opened 20/20 sequence remains labeled only as a search/click sub-gate.

## Delivered

- Made the canonical CDP controller the sole production mutation route for click.
- Enforced ordered grounding: unique stable selector, one exact accessibility identity, then explicitly verified screenshot coordinates.
- Bound screenshot fallback to a fresh screenshot hash, verified flag, viewport point, and compatible hit target.
- Added structured grounding attempts and fallback reasons to adapter traces.
- Added bounded exact post-click verification for WhatsApp chat headers, Gmail thread subjects, Google Docs titles, and Google Drive item headings.
- Extended the canonical contract and backend policy enforcement with the grounding policy.
- Repaired two runtime-launch bottlenecks: an unbounded PowerShell health probe and a false wrapper-PID/server-PID mismatch. Direct health preflight now prevents duplicate startup when Windows listener enumeration is restricted.
- Made explicit safe navigation the application-owned bootstrap path: a workflow may open an `http`/`https` destination from only Chrome New Tab or `about:blank`; other privileged origins remain blocked. The destination URL is preserved in the canonical contract and enforced by both extension and backend policy.
- Prevented a new Analyze submission from inheriting a restored workflow session. New tasks now receive a fresh session/idempotency namespace; Resume alone retains the existing session.
- Removed a development auto-reload parent/worker pair that was silently recreating a `local-dev` backend after the canonical worker stopped. The validation runtime is now one non-reloading process.
- Added a centralized destination resolver for trusted known applications and evidence-first discovery for unknown named destinations. High-confidence verified public sites may open automatically; ambiguous, account-sensitive, and risky destinations pause.
- Added capability-aware compound-objective routing. Completed objectives survive tab changes, and incompatible requests such as media playback inside Gmail produce a clarification instead of an internal search loop.
- Added bounded semantic recovery and meaningful user-facing terminal outcomes. Consequential, uncertain, policy-blocked, and confirmation-bound actions never enter automatic recovery.
- Repaired two validation defects exposed by the complete suite: the production red-team harness now supplies the mandatory immutable execution contract, and popup reconciliation no longer orphans `target=_blank` or `window.open()` pages.

The production invariant is documented in [trusted-grounding-and-postconditions.md](../../stabilization/trusted-grounding-and-postconditions.md).

## Automated verification

- Extension TypeScript type-check: passed.
- Production extension build: passed.
- Extension full suite: **173/173 passed** after the Run 2 navigation-message regression was added.
- Backend Day 3 focused/regression suite: **135/135 passed**.
- Backend full suite: **4499/4499 passed**.
- Real-Chromium popup gate: **4/4 passed**, then passed again inside the focused regression run.
- Production-evidence/red-team gate: **8/8 passed**.
- Final focused backend gate for grounding, destination resolution, blueprint intent, and convergence: **53/53 passed**.
- Final focused extension gate for completion, canonical contract, runtime handshake, and message validation: **22/22 passed**; TypeScript type-check and production build passed.
- Canonical runtime/extension handshake during final certification: URL `http://localhost:8000`, server PID `6032`, build `stabilization-20260821T054320Z`, commit `ee8c8d9`.

## Promoted live API robustness probes

All probes were sent to the promoted canonical process through `POST /analyze`; no browser mutation was performed by these API-only checks.

| Synthetic instruction / state | Live result |
|---|---|
| `Play Telugu music on YouTube` from New Tab | Safe `navigate` intent to `https://www.youtube.com/`; status `waiting_browser`. |
| `Open Gmail and play Telugu music` after verified Gmail navigation | Safe `open_new_tab` intent to YouTube; completed Gmail objective preserved. |
| `Play Telugu music inside Gmail` | `ask` outcome explaining Gmail lacks media playback and offering YouTube; zero actions. |
| `Open RBVRRIT college Portal` from New Tab | Safe navigation to a Google evidence search; no portal URL guessed. |

## Live WhatsApp findings

The authenticated Chrome session loaded WhatsApp and exposed the exact direct chat plus two group-reference occurrences of the same text.

| Observation | Result | Root cause / disposition |
|---|---|---|
| Exact direct-chat row click followed by exact header/composer check | Passed in live Chrome | Accessible row grounding distinguished the direct chat; exact header and `Type a message to Teja Spc` composer were visible. |
| Five reload-based repetitions | Failed before click | WhatsApp remained in encrypted message restoration longer than the original ready-state deadline; no click or send occurred. The UI became ready after about 34 seconds. |
| Ten accessibility-only search-control reacquisitions | Failed before click | WhatsApp removes the search textbox's accessible name after it contains a query. This supports stable-selector-first grounding for the control. |
| Plain exact-text click after another chat was selected | No effect / wrong occurrence rejected by postcondition | `Teja Spc` also appeared inside group-reference text. Anchoring to the chat row fixed the ambiguity. |
| Broad diagnostic contenteditable selector | Recovered, no send | It selected the message composer and created the unsent draft `BCA Prathiksha`. The draft was immediately cleared with Select All + Backspace; the UI returned to an empty composer and Voice message control. Nothing was sent. This selector is not allowed by the production exact-identity click contract. |

Live side-effect totals: messages sent **0**; files attached **0**; duplicate effects **0**; recovered unsent drafts **1**.

## Application-side-panel acceptance attempts

| Run | Result | First failing step | Root cause / correction | Side effects |
|---:|---|---|---|---|
| 1 | Failed safely | New Tab to WhatsApp navigation was rejected before mutation. | Chrome and API were running a newly rebuilt `dev/local-dev` pair created by an ordinary extension build plus `backend/run.py`; that script still launched a reload parent/worker. The workflow event then identified `execution_contract_target_mismatch`: the contract converted the navigation action's empty selector from `""` to `null`. `backend/run.py` now forwards to the canonical launcher, the launcher refuses noncanonical runtimes, and selector identity is preserved byte-for-byte. The corrected contract passed both live policy stages on build `stabilization-20260819T070526Z`. | Messages 0; attachments 0; navigation 0; duplicates 0. |
| 2 | Failed safely | The extension's internal execution-message validator rejected the navigation contract before policy or mutation. | Backend `SuggestedAction` serialization represents absent grounding as `{}`. The validator interpreted any present object as element grounding and required a `source`. The canonical builder now normalizes only an empty object to absent grounding; non-empty malformed grounding and screenshot claims remain fail-closed. The terminal report also incorrectly blamed network/sign-in and unverifiable search evidence; failure-class-aware reporting now identifies internal validation, policy, authentication, network, no-effect, and generic execution failures separately. Exact New Tab to WhatsApp contract/internal-message regressions and a promoted API replay pass on build `stabilization-20260819T072258Z`. | Messages 0; attachments 0; navigation 0; duplicates 0. |
| 3 | Failed safely (automated side-panel) | With WhatsApp already open, the destination resolver treated `open the exact direct chat...` as an unknown website and proposed a Google search. | Page-local objects such as chats, contacts, threads, documents, files, and folders are now excluded from website discovery after their containing application is resolved. The exact prompt is regression-covered from both New Tab and an already-open WhatsApp page. | Messages 0; attachments 0; duplicate effects 0. |
| Auth-boundary replay | Passed expected safety outcome (automated side-panel) | The isolated validation profile's WhatsApp authentication had expired. | The application now detects the QR/login screen before control selection, returns `needs_info` in 20.6 seconds, proposes zero actions, performs no retry, and explains that WhatsApp must be linked. Recipient parsing also stops at the trailing `Do not...` safety sentence, preserving exact identity `Teja Spc`. | Messages 0; attachments 0; duplicate effects 0. |

Runs 1 and 2 are not counted toward the required 20 consecutive passes. They are retained as failure evidence rather than erased from the record.

## 20/20 authenticated application-side-panel certification

The user authenticated the project-owned persistent validation profile by scanning WhatsApp's QR code. A fresh sequence then ran the natural-language instruction 20 consecutive times through the real extension side panel. A later harness audit found that `_initial_target_url()` pre-opened WhatsApp based on the prompt before each submission, so this sequence is retained only as evidence for exact-chat grounding/click verification and zero-send behavior; it is not New Tab destination-resolution evidence:

`Open WhatsApp and open the exact direct chat named Teja Spc. Do not type a message, attach a file, or send anything.`

| Gate | Result |
|---|---:|
| Completed runs | 20/20 |
| Runs with exactly two actions | 20/20 |
| Runs observing `Type a message to Teja Spc` | 20/20 |
| Screenshot pairs captured | 20/20 |
| Attach/upload/send/file-chooser actions | 0 |
| Duplicate external effects | 0 |
| Minimum / average / p95 / maximum latency | 27.8 / 32.44 / 37.4 / 42.6 seconds |

Each run used stable-selector grounding for the recipient row, trusted CDP input for the click, and the exact WhatsApp postcondition before completion. The final screenshot visually confirms the `Teja Spc` header and an empty `Type a message` composer. Raw aggregate evidence is in [day3-cert-20-run.json](../live_sidepanel/day3-cert-20-run.json); per-run side-panel and target screenshots are stored beside it as `day3-cert-01` through `day3-cert-20`.

After certification, one final presentation-only smoke run passed in 27.2 seconds with the same two actions and exact composer evidence. It confirmed the completed UI no longer displays the contradictory `Semantic progress has stalled` notice.

The failures retained before certification exposed four distinct root causes: a non-actionable title-span click, negative safety text misclassified as an upload objective, verified post-click evidence not reaching convergence, and optional diagnostics being stripped at a message boundary. The final design promotes the click to the unique containing chat row, normalizes negative clauses centrally across planning layers, and completes an open-only exact-target task at the side-panel controller immediately after the service worker's postcondition-gated success. No failed attempt is counted in the 20/20 result.

## Corrected genuine-New-Tab certification

On 2026-08-21, the operator authenticated the isolated project profile in the same browser process used by the harness. The harness was corrected to separate an optional operator-setup URL from the measured initial URL and to wait until React completed a workflow reset before filling the prompt. This removed two validation errors: authenticating the wrong browser profile and racing a still-disabled prompt after `Clear`.

The corrected natural-language instruction then completed 20 consecutive real extension-side-panel runs. Every measured run began at `chrome://newtab/`; the harness did not pre-open or inject the destination URL.

| Gate | Result |
|---|---:|
| Completed runs | 20/20 |
| Genuine `chrome://newtab/` initial states | 20/20 |
| Exact action sequence: navigate, search fill, trusted click | 20/20 |
| Trusted CDP click using `stable_selector` grounding | 20/20 |
| Exact entity-specific composer observed | 20/20 |
| File-chooser / attach / upload / send actions | 0 |
| Extra or duplicate action sequences | 0 |
| Minimum / average / p95 / maximum latency | 29.6 / 38.81 / 42.3 / 43.0 seconds |

The strict post-run audit found no anomalous run. Raw aggregate evidence is in [day3-newtab-cert-20-run.json](../live_sidepanel/day3-newtab-cert-20-run.json), and the final target screenshot is [day3-newtab-cert-20-target.png](../live_sidepanel/day3-newtab-cert-20-target.png).

## Expanded robustness checkpoint

Product-intent review showed that an explicit URL in the WhatsApp validation prompt would mask a general navigation gap. Day 3 therefore requires natural-language destination resolution, compound-objective decomposition, capability/site compatibility checks, ambiguity clarification, bounded semantic recovery, and meaningful terminal responses before the 20/20 run. That engineering and automated robustness checkpoint is now complete.

This checkpoint is informed by the documented ChatGPT/Codex browser behavior as a reference product: browser navigation and multi-step website interaction, web search, existing-Chrome operation through an extension, shared visible state, and user control. It does not assume or copy undocumented private implementation details.

Acceptance cases are maintained in the main 15-day plan and cover natural-language destination resolution, compound tasks, incompatible site/capability combinations, ambiguous named portals, unverifiable destinations, and bounded failure handling. Automated tests, promoted live API probes, retained live side-panel robustness evidence, and the corrected actual-browser mutation gate passed.

## Day 4 entry condition

Day 3's mandatory live gate is closed. Day 4 may begin with explicit synthetic-file selection, destination binding, attachment-preview verification, and the existing rule that nothing is sent without confirmation.
