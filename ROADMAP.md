# Version 1 roadmap (proposed)

This is a sequence of evidence gates, not a promise that calendar time alone makes the product ready. See `TASKS.md` for current status and `TESTS.md` for proof. Booking is a diagnostic end-to-end case; implementation stays site-neutral.

| Week | Milestone | Exit evidence |
|---|---|---|
| 1 | Freeze the initial release capability and one complete test workflow; establish the real side-panel baseline | Exact first failing step and reproducible evidence for every attempted run |
| 2 | Make page reading and exact target binding reliable | Dynamic controls, dates, loading, and wrong-target tests pass |
| 3 | Connect goal state, one-step planning, verification, and bounded recovery | No-progress loops stop; final claims require goal evidence |
| 4 | Enforce privacy, confirmation, and restart safety; improve UI feedback | No secret leakage or duplicate consequential effects in controlled tests |
| 5 | Repeat live end-to-end runs, fix root causes, package pilot | Chosen workflow meets release gate, tests/build pass, rollback and installation instructions work |

The first implementation plan is written in Phase 5 and needs owner approval before code changes. Large or safety-related tasks also require the task-specific approval described in `AGENTS.md`.

## Deployment-ready definition

- The supported workflow and sites are stated plainly; unsupported cases stop honestly.
- The real extension side panel, backend, and database complete the chosen task repeatedly with final evidence. Fixture and Playwright-only results are supporting tests.
- Zero wrong-target commitments, duplicate final submissions, safety bypasses, or false completion claims in counted release runs.
- Extension type-check/tests/build and relevant backend tests pass; version identities match; no unexplained failure remains.
- Installation, configuration, privacy statement, known limitations, logging, and rollback steps are documented.

## Later versions

- **Version 2:** additional task families, opt-in private-site access, stronger visual understanding, more complex travel flows, and user preference memory.
- **Version 3:** broader supported-site certification and optional integrations. Payment or other irreversible actions require separate safety design and approval, not an automatic version upgrade.

