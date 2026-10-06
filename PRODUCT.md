# Product direction

## Vision and first user

The assistant helps a person complete an authorized web task in Chrome and shows what happened. The first tester is the project owner. A useful result is the requested end state backed by browser evidence, or an honest explanation of why the task stopped.

## Version 1 scope proposed for planning

- One general workflow loop: understand the goal, read the current page, choose one step, act, observe, verify, and recover or stop.
- Reusable browser capabilities for navigation, search, exact selection, date and option controls, forms, and multi-page progress. Website names are task data, not core branches.
- Short-term task state, clear progress, bounded retries, policy checks, and a final evidence-based result.
- A travel booking task is a demanding **evaluation example**. A complete no-charge test booking must reach a confirmed reservation; a search result or payment page is incomplete.
- Limited AI input from public pages: title, URL, and small relevant text snippets. Private account pages remain excluded until the owner makes a separate data decision.

The exact release workflow and supported sites will be selected in the Phase 5 implementation plan after feasibility checks. This document does not change the older four-workflow pilot freeze or authorize a production booking.

## Explicit non-goals for initial Version 1

Universal website support; autonomous payment; password or one-time-code handling; CAPTCHA bypass; message sending; cancellation or deletion; long-term personal browsing memory; silent action retries after an uncertain external effect. These require separate scope and safety approval.

## User stories

1. As a user, I can state a multi-step goal and see what the assistant is trying to do now.
2. As a user, I can see the exact site, date, person, price, and consequence before approving a real-world commitment.
3. As a user, I receive a verified completion result or a clear partial/blocked result.
4. As a tester, I can identify the first failing step and reproduce it without guessing.

## Success criteria

- The chosen release workflow passes its repeated live side-panel gate, including final-state verification; thresholds are finalized in Phase 5.
- Zero wrong-target commitments, duplicate consequential submissions, policy bypasses, or false completion claims in counted tests.
- Every counted run has a result, first-failure classification, timing, and evidence reference.
- The extension and backend build, pass relevant tests, and show matching runtime identities.

