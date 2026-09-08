# Days 13–14 — Cross-domain Conformance Progress

**Recorded:** 2026-09-08  
**Status:** IN PROGRESS — the foundation release gate is not yet complete

## Results on the current generic path

| Scenario | Surface | Result | Time | Mutations | Retries / duplicates |
|---|---|---:|---:|---:|---:|
| Public destination + field fill + exact activation + result verification | Wikipedia | PASS | 37.0 s | navigate, fill, click | 0 / 0 |
| Delayed content + duplicate prose + dialog + exact final state | Neutral local fixture | PASS | 43.9 s | navigate, click, click | 0 / 0 |
| Read-only public destination + visible marker | Example Domain | PASS | 37.2 s | navigate | 0 / 0 |
| Authentication boundary | Neutral local fixture | PASS (`needs_intervention`) | 33.0 s | navigate only | 0 / 0 |

Every browser mutation above travelled through the extension side panel and the canonical gateway. The live harness did not directly click or fill the target page. The authentication run intentionally stopped before the synthetic human action.

## Defects found and corrected during these runs

1. Two observation extractors described one DOM button with different CSS selectors. The merge treated them as two controls and repeatedly asked the user to disambiguate. The extension now collapses selector aliases only when both selectors resolve uniquely to the same live DOM node; distinct same-name nodes remain ambiguous.
2. An optional public `Log in` link was treated as a blocking authentication gate after a successful search. Authentication, MFA, and CAPTCHA suspension now require structural interactive evidence instead of untrusted article prose or headings alone.
3. The live harness classified a legitimate human-intervention checkpoint as a timeout. It now records `needs_intervention` immediately.
4. The rolling live report could erase the only JSON result for an earlier task. Each task now also receives a task-scoped machine-readable evidence file.
5. Seven policy timestamp errors remained even though Alembic reported the old head. A forward migration converted the seven UTC policy timestamps to PostgreSQL `timestamp with time zone`; the validator was also corrected to compile inspected types with the active dialect instead of losing the timezone flag through `str(type)`.
6. The first structural-only authentication refinement became too strict for a credential-free human gate and produced one failed diagnostic run (`gf-d1314-auth-pause-02`). The corrected rule requires a required-auth heading plus a matching interactive control, a credential field plus auth control, a password field, or QR instructions plus a QR/link-device control. The following live run (`gf-d1314-auth-pause-03`) passed as `needs_intervention` in 33.0 seconds.

## Regression results

- Focused backend foundation/policy/intervention/orchestrator suite: **219 passed**.
- Full extension suite: **232 passed**.
- Extension TypeScript check: **passed**.
- Extension production build: **passed**.
- Infrastructure validation: **passed** (`schema_errors=0`, `schema_warnings=0`, Alembic current/head `20260908_0004`, 18 contracts compatible, 0 serialization failures).

## Evidence

- `docs/production_validation/live_sidepanel/gf-d1314-public-search-07.json`
- `docs/production_validation/live_sidepanel/gf-d1314-public-search-07-target.png`
- `docs/production_validation/live_sidepanel/gf-d1314-dynamic-08.json`
- `docs/production_validation/live_sidepanel/gf-d1314-dynamic-08-target.png`
- `docs/production_validation/live_sidepanel/gf-d1314-public-read-02.json`
- `docs/production_validation/live_sidepanel/gf-d1314-public-read-02-target.png`
- `docs/production_validation/live_sidepanel/gf-d1314-auth-pause-03.json`
- `docs/production_validation/live_sidepanel/gf-d1314-auth-pause-03-target.png`

## Remaining before the Days 13–14 exit

- Complete the capability matrix for native forms, select/date widgets, frames, pagination/scroll, tab lifecycle, verified download, and production-owned content insertion.
- Run unseen/randomized DOM variants for each mutation family.
- Complete restart/resume and stale-target live variants with duplicate-effect accounting.
- Complete prompt-injection, cross-origin, account-confusion, and privileged-URL live safety cases.
- Validate two structurally different real services for each capability where the action is safe and authorized.

Day 15 and the original upload/send certification remain blocked until this matrix is complete.
