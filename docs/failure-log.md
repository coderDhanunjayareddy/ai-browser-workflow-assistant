# Failure log template

## 2026-10-06 — search prerequisites and bounded observation diagnostic

| Field | Record |
|---|---|
| Runtime | `stabilization-20261006T063145Z`, real Chromium extension side panel and canonical backend. |
| Task | Hyderabad to Delhi, 20 October 2026, one adult; cheapest available option, stopping before login, personal details, payment, or final submission. |
| First live failures | `BOOKING-MMT-PREREQ-03` clicked a Delhi–Pune link after two refresh waits; `PREREQ-04` reached the correct route but paused while its departure control still showed 7 October; `PREREQ-06` paused on an ungrounded route link on `/flights/`; `PREREQ-08` reached the route but the 150-control observation omitted `#departure`, so a stale date selector failed CDP grounding. |
| Environment-limited reruns | `PREREQ-05` stopped at a browser error page on initial navigation. `PREREQ-07` and `PREREQ-09` had an initial navigation `no_effect`; the app reported incomplete work. The harness incorrectly labelled those reports `completed`; its terminal classification is now corrected and unit tested. |
| Root cause supported by evidence | The selected date was not represented as a required precondition before result choice. Dense-page extraction omitted a visible date input from the 150-element page context. The existing action identity check could accept a wrong route link when the planner's own description matched that link, even though it conflicted with the user's route. |
| Fix in progress | Generic requested-date evidence and route-page ordering, unique observed date-control and full-date-option continuation, priced-result precondition, wrong-route link block, and bounded goal/form-control observation. No site-specific selector or second browser dispatch was added. |
| Verification | 3,810 backend unit tests passed with two known stale inventory/fixture-count checks excluded; 256 extension tests, type-check, and build passed. A stored live route-page observation replay grounded the current `#departure` control. Final live success is not established. |
| Safety | No flight, booking, payment, personal data, or login was submitted. Human-checkpoint browser sessions remain open. |


## 2026-10-06 — target guard held; date and search progress remain unverified

| Field | Record |
|---|---|
| Date/time and runtime build | 2026-10-06 09:10 IST; `stabilization-20261006T034010Z`, `713d680-dirty` |
| Website and environment | MakeMyTrip public flight route page, fresh Chromium profile, real unpacked extension side panel; browser remains paused. |
| User task | One-way Hyderabad to Delhi for 20 October 2026, one adult; stop before login, personal data, payment, or final booking submission. |
| Expected final result | Correct route, verified date and traveler selection, cheapest option, then safe boundary or honest stop. |
| Actual result | The app dismissed the optional overlay and reached `https://www.makemytrip.com/flights/hyderabad-new_delhi-cheap-airtickets.html`. Its date-control click failed exact CDP grounding. It later clicked a search control without verified flight-result progress, then proposed a Delhi–Pune link as the cheapest Hyderabad–Delhi option. The authoritative identity check converted that proposal to an ask before browser dispatch. No flight was selected or booked. |
| First failed action and step number | After route navigation, click `[data-cy="departureDate"]`: `CDP could not ground the requested target without changing its identity.` The later wrong-link proposal was safely blocked. |
| Page state before / after | Seven recorded observations stayed on the requested Hyderabad–Delhi route after navigation. The browser and workflow remain open at a missing-information pause. |
| Screenshot or trace path | Backend mission `f8d7f936-0d3d-4e08-a588-140b55b47afc`; canonical backend log `docs/production_validation/day1/runtime/stabilization-20261006T034010Z.stdout.log`. The live harness has not finalized its JSON because the browser is still paused. |
| Failure class | Date-widget grounding / action-level verification / search-result observation. |
| Root cause and evidence | Exact date target was present in the planned selector but CDP could not ground it at execution time. A search-control click was reported successful without final search-result evidence. The wrong proposed Delhi–Pune link was blocked by the new selector-to-description identity check; its cause still needs investigation. |
| Fix or safe workaround | Pending next task: inspect the observed date widget and search effect contract, then implement generic widget interaction and postcondition verification. Do not add a site-specific selector or infer success from a click. |
| Regression test | Target guard: 3,800 backend unit tests passed with two unrelated pre-existing tests excluded; extension type-check, 255 tests, and build passed. Date/search cases pending. |
| Real side-panel rerun result | Target identity fix passed its live safety check; complete booking diagnostic failed. |

The previous live run `BOOKING-MMT-IDENTITY-01` also reached the correct route and paused after a date action was repaired to an unrelated Ahmedabad–Goa link. Ledger evidence identified `Semantic Execution Kernel` as the source of that replacement. The kernel repair now requires target-label agreement, and `BOOKING-MMT-IDENTITY-02` did not execute such a replacement.

Final target-identity build `stabilization-20261006T034601Z` was rerun as `BOOKING-MMT-IDENTITY-03`. Its only executed browser actions were navigation to MakeMyTrip, dismissal of the optional overlay, and the exact Hyderabad–Delhi route link. The app observed `https://www.makemytrip.com/flights/hyderabad-new_delhi-cheap-airtickets.html`, then paused before dispatching a proposed Delhi–Pune link described as the cheapest Hyderabad–Delhi option. The browser and workflow remain open. This validates refusal of the wrong target in the final build; it does not validate date selection or booking completion.


## 2026-10-06 — wrong flight link accepted under a date-selection action

| Field | Record |
|---|---|
| Date/time and runtime build | 2026-10-06 08:34 IST; `stabilization-20261006T025055Z`, `713d680-dirty` |
| Website and environment | MakeMyTrip public homepage and flight page, fresh Chromium profile, real unpacked extension side panel. |
| User task | One-way Hyderabad to Delhi for 20 October 2026, one adult; stop before login, personal data, payment, or final booking submission. |
| Expected final result | Correct route and date selected from observed controls, or a safe stop on uncertain target. |
| Actual result | The app re-observed a late sign-in overlay, clicked its exact close control once, and verified it disappeared. It then used unrelated flight-link targets while planning the requested route/date. The browser reached an Ahmedabad–Goa flight page. Later date-control attempts failed or produced no relevant result. No booking was made. |
| First failed action and step number | Step 2 requested a Hyderabad–Delhi flight link, while execution evidence includes `[data-cy="anchor-ahmedabad-to-goa-flight-317"]`. Step 4 labelled a departure-date selection targeted a flight link instead of a date control. |
| Page state before / after | Homepage after overlay dismissal, then `https://www.makemytrip.com/flights/ahmedabad-goa-cheap-airtickets.html`; the requested Hyderabad–Delhi route was not observed. |
| Screenshot or trace path | `docs/production_validation/live_sidepanel/booking-mmt-recovery-01.json` and `booking-mmt-recovery-01-target.png`. |
| Failure class | Planning / semantic grounding / action identity / false action-level verification. |
| Root cause and evidence | The grounded click targets in the durable execution record conflict with the action descriptions. `backend/app/grounding/resolver.py` grants enough confidence to a selector match and generic click compatibility even when the target label conflicts with the described intent. `bindObservationGrounding` can add the selected element's name after the planner chose the selector. Exact causality of each delayed navigation remains to be traced; the wrong target identities and wrong route are directly observed. |
| Fix or safe workaround | Pending owner approval for a task-specific plan: reject identity mismatches at the authoritative grounding boundary; preserve action and target identities through verification; do not substitute another link. |
| Regression test | Pending controlled route/date controls with many similarly named links, followed by a real side-panel rerun. |
| Real side-panel rerun result | Failed after the overlay dismissal succeeded. No real booking submission or payment occurred. |


## 2026-10-06 — late overlay made the observed click target stale

| Field | Record |
|---|---|
| Date/time and runtime build | 2026-10-06 08:20 IST; `stabilization-20261006T025055Z`, `713d680-dirty` |
| Website and environment | MakeMyTrip homepage, fresh Chromium profile, real unpacked extension side panel, canonical backend. |
| User task | Same one-way Hyderabad to Delhi diagnostic, stopping before login, personal data, payment, or final booking submission. |
| Expected final result | Continue public search where possible, or accurately stop at a required boundary. |
| Actual result | The side panel navigated successfully, then tried its planned Flights link. A sign-in overlay appeared between observation and click. The exact link was covered, CDP refused to change target identity, and the workflow stopped. No flight was selected or booked. |
| First failed action and step number | Step 2 click, `a[href="https://www.makemytrip.com/flights/"]`: `CDP could not ground the requested target without changing its identity.` |
| Page state before / after | Observed URL remained the homepage. The execution verifier recorded `modalCount: 1` before and after the failed click; the screenshot shows the overlay covering the link and public flight form. |
| Screenshot or trace path | `docs/production_validation/live_sidepanel/booking-mmt-overlay-01.json` and `booking-mmt-overlay-01-target.png`. |
| Failure class | Dynamic observation / stale grounding / recovery classification. |
| Root cause and evidence | The application observed the page before the overlay appeared. Its execution layer correctly refused an occluded target, but the side panel did not classify the exact CDP grounding failure as recoverable, so it never re-observed the new overlay. |
| Fix or safe workaround | Classify this exact target-grounding failure as a bounded safe-action re-observation. The existing recovery loop and target identity checks remain authoritative; no substitute click is allowed. |
| Regression test | `useWorkflow.routing.test.cjs` checks that the exact CDP failure enters the bounded target-not-found recovery path. Extension type-check, 255 tests, and build passed. |
| Real side-panel rerun result | `BOOKING-MMT-RECOVERY-01` re-observed the overlay and dismissed it once through the application, then failed on a separate wrong-target issue. |

The previous human-handoff browser remains open. Automatic approval review rejected closing it because doing so could discard its paused workflow state.

Copy the entry below for each meaningful live failure. Use test identities and redacted page text; never paste credentials, payment details, tokens, or private screenshots. A benchmark-only failure must be labelled as such.

## YYYY-MM-DD — short failure name

| Field | Record |
|---|---|
| Date/time and runtime build | |
| Website and environment | |
| User task (redacted if needed) | |
| Expected final result | |
| Actual result | |
| First failed action and step number | |
| Page state before / after | URL, title, loading state, target identity; redact private text |
| Screenshot or trace path | Local evidence reference, or `none` |
| Failure class | observation / planning / grounding / execution / verification / recovery / policy / environment |
| Root cause and evidence | Known cause, or `unconfirmed` with the next check |
| Fix or safe workaround | |
| Regression test | |
| Real side-panel rerun result | pass / fail / pending; never infer from a fixture |

## 2026-10-06 — optional-looking sign-in overlay halted public flight search

| Field | Record |
|---|---|
| Date/time and runtime build | 2026-10-06 07:16 IST; `stabilization-20261006T013642Z`, `713d680-dirty` |
| Website and environment | MakeMyTrip public homepage in real unpacked extension Chromium run, with the URL supplied in the user task; application started from `chrome://newtab/`. |
| User task | Search one-way Hyderabad to Delhi flight for 20 October 2026, one adult, choose the cheapest option, and continue only to the login, personal-data, payment, or final-submission boundary. |
| Expected final result | Flight search and selection progress with observed evidence, or a verified required human boundary. |
| Actual result | Navigation to MakeMyTrip succeeded. The application immediately declared an authentication gate and waited for a human; no flight search action occurred. The screenshot shows a sign-in overlay with a visible close icon and the flight form behind it. Whether public search continues after dismissal was not tested. |
| First failed action and step number | After Step 1 navigation, the next analysis produced `HUMAN STEP REQUIRED` without trying to resolve the overlay through the application. |
| Page state before / after | Before: New Tab. After: MakeMyTrip homepage with sign-in overlay; `#fromCity` and `#toCity` were present in the captured control metadata. |
| Screenshot or trace path | `docs/production_validation/live_sidepanel/booking-mmt-01.json`; `booking-mmt-01.png`; `booking-mmt-01-target.png` in the same directory. |
| Failure class | Perception / authentication-gate classification / recovery. |
| Root cause and evidence | The deterministic gate check in `workflow_orchestrator.py` treats a visible credential field plus sign-in control as blocking authentication. The application captured the homepage and flight fields but did not distinguish the dismissible overlay from a required gate. The close icon is visible in the screenshot but absent from the first 80 captured control records; exact DOM grounding remains unconfirmed. |
| Fix or safe workaround | Implemented generic close-control extraction and a single reversible dismissal before human handoff, with a public-control and prior-attempt check. No credentials are entered. |
| Regression test | Optional overlay versus required-auth and challenge cases passed in the backend focused suite (168 relevant tests); extension type-check, 255 tests, and build passed. |
| Real side-panel rerun result | `BOOKING-MMT-RECOVERY-01` observed and dismissed the close control through the application; the overlay disappeared. The booking task then failed on a separate wrong-target issue. `BOOKING-MMT-HANDOFF-01` remains paused in its browser. |

The `BOOKING-MMT-01` validation driver closed Chromium when the extension returned `needs_intervention`, although the extension itself showed `Waiting for you` and a `verify and resume` control. This was a driver lifecycle defect. The subsequent driver run uses `--hold-on-human` and keeps the browser and workflow open while awaiting the owner's action.

## 2026-10-06 — booking diagnostic chose an unverified destination

| Field | Record |
|---|---|
| Date/time and runtime build | 2026-10-06 07:08 IST; `stabilization-20261006T013642Z`, `713d680-dirty` |
| Website and environment | Real unpacked extension in Chromium, canonical local backend, public web; application started from `chrome://newtab/` |
| User task | Find a one-way Hyderabad to Delhi flight for 20 October 2026, one adult; choose the cheapest option and proceed only to the login, personal-data, payment, or final-submission boundary. |
| Expected final result | A flight option and booking progress backed by live page evidence, or an accurate safe stop at a required boundary. |
| Actual result | Step 1 navigated to `https://www.exampleflightbooking.com`; Chromium showed `DNS_PROBE_FINISHED_NXDOMAIN`. The side panel stopped with a browser-error message. No flight was selected or booked. |
| First failed action and step number | Step 1, `navigate` to a planner-supplied placeholder destination. |
| Page state before / after | Before: New Tab, `chrome://newtab/`, no page controls. After: `chrome-error://chromewebdata/`, title `www.exampleflightbooking.com`, DNS error text. |
| Screenshot or trace path | `docs/production_validation/live_sidepanel/booking-baseline-02.json`; `booking-baseline-02.png`; `booking-baseline-02-target.png` in the same directory. |
| Failure class | Destination discovery / planning, followed by false action-level verification. |
| Root cause and evidence | The planner supplied a destination absent from the user task and observed page. The action verifier recorded `verified: true` because the URL changed, even though the target page was a Chrome error page. Why the existing destination resolver did not handle this category remains to be confirmed during the approved implementation task. |
| Fix or safe workaround | Pending. Propose a generic destination discovery rule requiring user-supplied or independently observed URL evidence before navigation, plus navigation verification that rejects browser error pages. Do not add a flight-site branch. |
| Regression test | Pending: controlled unknown-destination fixture, error-page postcondition, then the same real side-panel task. |
| Real side-panel rerun result | Fail; this was the first network-enabled application run. No runtime code changed. |

## 2026-10-06 — sandboxed backend could not reach AI provider

| Field | Record |
|---|---|
| Date/time and runtime build | 2026-10-06 07:04 IST; `stabilization-20261006T013158Z` |
| Website and environment | Real unpacked extension in Chromium, backend launched inside restricted command sandbox. |
| User task | Same booking diagnostic as above. |
| Expected final result | Planner starts the application workflow. |
| Actual result | Side panel stopped at analysis; backend returned three HTTP 503 responses; no navigation occurred. |
| First failed action and step number | Initial planner request, before Step 1. |
| Page state before / after | New Tab remained open. |
| Screenshot or trace path | `docs/production_validation/live_sidepanel/booking-baseline-01.json` and `booking-baseline-01.png`. |
| Failure class | Test environment. |
| Root cause and evidence | The configured provider endpoint was unreachable from the restricted command sandbox and returned HTTP 200 from the approved outbound environment. Rebuilding and launching the same backend with outbound access allowed Step 1 planning on the next run. |
| Fix or safe workaround | Run the canonical backend with outbound access for live tests; no application patch. |
| Regression test | Health handshake plus a real side-panel analysis request. |
| Real side-panel rerun result | Passed planner startup in `BOOKING-BASELINE-02`; the workflow then failed at destination discovery. |
