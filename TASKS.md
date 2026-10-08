# Project task board

Updated: 2026-10-06. Planning phases are separate from implementation. Do not mark a live workflow complete from unit or controlled-fixture results alone.

## Current task

| Task | Status | Acceptance criteria |
|---|---|---|
| Multi-step search prerequisites and dynamic observation | In progress; live end-to-end gate not passed | The approved route, date, and result prerequisites passed local tests. `BOOKING-BUS-PREREQ-28` verified both cities, a committed 20 October result URL, the observed Price sort, and entry to a FlixBus seat map through the real side panel. It stopped after selecting one seat when the planning service failed. The selected seat carried a male-only restriction despite unspecified passenger gender. Traveler eligibility, a defensible final fare, and the human boundary still need a separately approved follow-up. No booking completion is claimed. Evidence: `docs/failure-log.md`. |
| Single-traveler seat eligibility and fresh observation | Implemented locally; live gate failed | The approved follow-up now chooses only an observed eligible seat, preserves its full accessible identity, and forces a fresh observation after browser mutations. The real side panel reached an eligible seat in `BOOKING-BUS-SEAT-31`, but CDP could not execute the click because of a truncated target name; the truncation was corrected afterward. Runs 33 and 34 repeatedly stopped after a verified Price sort because the next control was stale or unavailable. Seat selection and the human boundary remain unverified. Evidence: `docs/failure-log.md`. |
| Exact target identity enforcement | Implemented; live safety check passed | The earlier approved fix passed `BOOKING-MMT-IDENTITY-03`; the booking diagnostic remains incomplete. |

The owner clarified that human interventions must pause the same live workflow, notify them, and resume after their step. The first MakeMyTrip run exposed a test-driver lifecycle defect: the extension displayed `Waiting for you`, but the driver closed Chromium. The driver now has an opt-in `--hold-on-human` mode; a live run is held open to verify continuation after owner action. This change is limited to the validation script, not the extension's booking behavior.

`BOOKING-BUS-PREREQ-17` is running through the real side panel on a second public booking site because MakeMyTrip's test-browser navigation currently fails. It is paused at the application's `Waiting for info` state with its interactive driver and browser open. The terminal outcome and requested detail have not yet been captured, so this is not a pass or a diagnosed failure.

The generic optional-overlay task passed its local checks and live overlay-dismissal check in `BOOKING-MMT-RECOVERY-01`. The extension re-observed a late popup and clicked one exact close control; the popup disappeared. A separate wrong-target failure stopped the route/date workflow. The older `BOOKING-MMT-HANDOFF-01` browser remains paused at its human checkpoint. The next task must prevent a planner description and selected control from diverging; no site-specific travel rule or new dispatch path is intended. Separate later tasks cover unproven destination provenance from `BOOKING-BASELINE-02` and action-level verification of Chrome error pages.

### Proposed next task: reject mismatched target identity

- **Goal:** refuse a planned action when its stated target identity conflicts with the exact observed control; retain the original tab, origin, frame, selector, action ID, and expected effect through dispatch and verification.
- **Affected files:** inspect and, where needed, change `backend/app/grounding/resolver.py`, `backend/app/orchestrator/workflow_orchestrator.py`, `extension/src/sidepanel/hooks/useWorkflow.ts`, and the existing canonical action contract or executor only if traces show identity changes there. Add focused cases to `backend/tests/unit/test_generic_semantic_grounding_conformance.py`, `backend/tests/unit/test_v3_intent_grounding.py`, and `extension/tests/useWorkflow.routing.test.cjs` as applicable.
- **Approach:** first reproduce a wrong selector paired with a named action in a controlled fixture. At the authoritative grounding boundary, reject or ask on a conflict between the requested accessible identity and the selected target label. A selector match alone must not confer authority to contradict the named goal. Re-observe once for stale safe controls; never select a merely similar route, date, or unrelated link. Verify a click by its declared effect, including a correct destination when the effect is navigation.
- **Tests:** run focused grounding, orchestration, and contract tests, all extension tests/type-check/build, relevant backend suite, then the same fresh-tab MakeMyTrip diagnostic through the real extension side panel. Record the first next failure in `docs/failure-log.md`.
- **Boundaries:** no website-specific selectors or route rules, new dispatch path, credential entry, private-page AI transfer, real booking submission, or payment. Preserve the paused human-handoff browser.
- **Approval and result:** approved by the owner. The authoritative resolver now refuses a selector whose observed label conflicts with an explicitly named action; the Semantic Execution Kernel no longer repairs a click to a merely plausible unrelated entity. Focused tests and 3,800 backend unit tests passed; two unrelated existing backend tests fail on inventory/fixture count drift. Extension type-check, 255 tests, and build passed. The final real side-panel safety check passed in `BOOKING-MMT-IDENTITY-03`; date/search workflow remains incomplete.

### Proposed next task: enforce multi-step search prerequisites and verify dynamic controls

- **Goal:** keep a multi-step search in its setup phase until the requested inputs are visibly selected; require an observed results list before selecting a result. For this diagnostic, select and verify the requested date and traveler count before any cheapest-flight choice.
- **Affected files to inspect before editing:** the goal and phase state in `backend/app/orchestrator/workflow_orchestrator.py` and `backend/app/execution_orchestrator/`; the real side-panel observation path in `extension/src/sidepanel/hooks/useWorkflow.ts`; canonical CDP targeting, effect verification, and generic widget adapters in `extension/src/`. Use existing contracts and one browser dispatch path.
- **Approach:** reproduce both observed failures in controlled dynamic-page fixtures: an exact date selector that CDP cannot click, and a result-selection proposal before the requested inputs/results are verified. Record selected values and the result-list identity from fresh page observations. Permit bounded re-observation and replan for a safe mismatched proposal; never click a related link as a substitute. Implement only the smallest shared capability supported by fixture and live evidence, without task- or site-specific branches.
- **Tests:** focused goal-state, widget/CDP, and postcondition tests; relevant backend tests; extension type-check/full tests/build; then the same MakeMyTrip task through a fresh real side panel. Record the first next failure.
- **Boundaries:** no MakeMyTrip selector in runtime code, no alternate dispatch path, no credential or private-page AI access, no payment or booking submission, and preserve paused browser sessions.
- **Approval and current result:** approved by the owner. The real side panel reached a correct 20 October result URL, selected Price sort, and opened a bus seat map in `BOOKING-BUS-PREREQ-28`. The complete workflow remains unverified after a planning-service error, and seat eligibility requires follow-up. Earlier diagnostic browsers were closed only when they had false missing-information states or the owner closed the window.

## Completed planning

| Task | Evidence |
|---|---|
| Phase 1 repository audit | Real request path traced; extension type-check and 255 tests passed; live gates identified as pending. |
| Phase 2 research mapping | Requested agent and benchmark sources mapped to product decisions. |
| Phase 3 target architecture | General task pipeline, gaps, data contracts, verification, recovery, and safety proposed and approved. |
| Phase 4 project documents | Eight requested files created; architecture schema parsed; production code untouched. |

## Next tasks after Phase 4 approval

| Task | Acceptance criteria |
|---|---|
| Phase 5: choose release proof and write implementation plan | One complete test workflow and its final proof are defined; first ten tasks each have files, dependencies, edge cases, tests, and manual checks. |
| Establish fresh side-panel baseline | Same runtime identity; first failure captured with page state, action, result, and final-goal status. |
| Implement the first approved task | Only its approved files change; relevant tests and manual check pass; limitation is reported. |

## Blocked decisions

| Decision | Current rule |
|---|---|
| Payment-required travel booking | Stop before payment and report incomplete until separately designed and approved. |
| AI access to private account pages | Excluded until the owner chooses a rule. |
| Production booking scope versus older four-workflow pilot freeze | No booking implementation or release claim until the Phase 5 plan explicitly revises scope and is approved. |
