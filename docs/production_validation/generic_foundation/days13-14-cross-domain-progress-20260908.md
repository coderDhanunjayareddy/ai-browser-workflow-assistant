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
| Compound native form: text, select, date, preview | Neutral local fixture | PASS | 36.4 s | navigate, fill, select, date, click | 0 / 0 |
| Pagination: offscreen, randomized control order, exact page identity | Neutral local fixture | PASS | 31.0 s | navigate, click | 0 / 0 |
| Delayed incremental collection with randomized control order (2 fresh profiles) | Neutral local fixture | PASS 2/2 | 30.1–31.2 s | navigate, click | 0 / 0 |
| Same-origin child frame: observe, exact bind, trusted click, same-frame verify | Neutral local fixture | PASS | 34.2 s | navigate, click | 0 / 0 |
| Tab lifecycle: distinct same-origin paths, new tab, exact-title return | Neutral local fixtures | PASS | 32.2 s | navigate, open new tab, focus existing tab | 0 / 0 |

Every browser mutation above travelled through the extension side panel and the canonical gateway. The live harness did not directly click or fill the target page. The authentication run intentionally stopped before the synthetic human action.

## Defects found and corrected during these runs

1. Two observation extractors described one DOM button with different CSS selectors. The merge treated them as two controls and repeatedly asked the user to disambiguate. The extension now collapses selector aliases only when both selectors resolve uniquely to the same live DOM node; distinct same-name nodes remain ambiguous.
2. An optional public `Log in` link was treated as a blocking authentication gate after a successful search. Authentication, MFA, and CAPTCHA suspension now require structural interactive evidence instead of untrusted article prose or headings alone.
3. The live harness classified a legitimate human-intervention checkpoint as a timeout. It now records `needs_intervention` immediately.
4. The rolling live report could erase the only JSON result for an earlier task. Each task now also receives a task-scoped machine-readable evidence file.
5. Seven policy timestamp errors remained even though Alembic reported the old head. A forward migration converted the seven UTC policy timestamps to PostgreSQL `timestamp with time zone`; the validator was also corrected to compile inspected types with the active dialect instead of losing the timezone flag through `str(type)`.
6. The first structural-only authentication refinement became too strict for a credential-free human gate and produced one failed diagnostic run (`gf-d1314-auth-pause-02`). The corrected rule requires a required-auth heading plus a matching interactive control, a credential field plus auth control, a password field, or QR instructions plus a QR/link-device control. The following live run (`gf-d1314-auth-pause-03`) passed as `needs_intervention` in 33.0 seconds.
7. Native selection initially produced no observable effect when CDP inserted text into a `<select>`. The trusted executor now drives type-to-select with CDP key events and Enter; the exact selected value is verified.
8. Native date assignment succeeded in the page but the action-specific verifier had no `choose_date` branch and retried the already-satisfied mutation. The verifier now accepts only an exact requested date value as the postcondition and rejects mismatches.
9. After the form assignments succeeded, broad control-name extraction reinterpreted `Priority` and `Due date` as extra click objectives. Compound-instruction bookkeeping now marks completed assignments separately and activation parsing no longer treats selection phrases as click commands. The final run performed five verified actions exactly once and reached `fixture_state=form_preview_ready_exactly_once`.
10. Pagination links sharing one destination were initially grounded by `href`, which erased their distinct identities. After the extractor preserved accessible selectors, the backend still concatenated duplicate identity fields (`Page 2 Page 2 Page 2`) and rejected an exact `Page 2` request. Exact grounding now compares each accessible identity field independently, requires a unique selector unless the task explicitly requests an ordinal, and preserves the exact link through the canonical CDP executor.
11. The substring `form` inside the fixture name `conformance` incorrectly selected a form workflow and diverted the objective into research-style recovery. Form capability classification now uses task-phrase boundaries, so URLs and unrelated words cannot silently change the workflow category.
12. Production observation previously inspected only the top document, while the worker explicitly rejected every non-top frame mutation. Observation now collects same-origin frame contexts, assigns each control an exact `chrome-frame:<id>` binding, preserves that binding through the canonical action contract, and runs post-action verification in the same frame. Cross-origin child content is excluded from merged observations.
13. An unquoted location qualifier was appended to a control name (`Continue inside the embedded workspace exactly once`), preventing exact grounding. Location phrases now qualify scope without changing the requested accessible identity. The live run bound `Continue` to `chrome-frame:8` and dispatched exactly one trusted CDP click.
14. The first tab-lifecycle diagnostic (`gf-d1314-tabs-01`) stopped after the first navigation because explicit destinations were considered complete by hostname alone. Two different paths on the same origin therefore collapsed into one objective. Explicit destination identity is now scheme, host, effective port, normalized path, and query sensitive (plus fragment when supplied). A deterministic, domain-neutral tab-focus stage also binds only one observed existing tab whose title exactly matches the user's requested title; it neither opens a substitute nor closes a tab.
15. After that correction, `gf-d1314-tabs-02` opened both same-origin/different-path destinations exactly once and verified the new-tab transition, then paused before focus because the bounded supplemental context placed executable tab inventory after larger narrative summaries. The side panel now prioritizes exact tab workspace identity before mission/workspace narrative, preventing context trimming from erasing the binding needed by a generic tab action. The diagnostic produced two successful mutations, zero retries, and zero tab closures.
16. The final tab-lifecycle run (`gf-d1314-tabs-03`) passed in 32.2 seconds. It executed exactly one navigation, one `open_new_tab`, and one `focus_existing_tab`; every durable action succeeded on its first non-retryable attempt. The tab-control verifier recorded `tab_switch_verified=true`, the following live observation reported `Neutral Framed Workspace` at the original URL, and the backend emitted an SGV-verified terminal report for that exact active title. Both requested tabs remained open and no close action occurred.

## Regression results

- Focused backend foundation/policy/intervention/orchestrator suite: **219 passed**.
- Full extension suite: **240 passed**.
- Focused child-frame/backend grounding suites: **106 extension checks and 70 backend checks passed**.
- Extension TypeScript check: **passed**.
- Extension production build: **passed**.
- Destination-resolution plus orchestrator regression suite after the tab-lifecycle correction: **55 passed** (including 22 destination cases).
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
- `docs/production_validation/live_sidepanel/gf-d1314-form-07.json`
- `docs/production_validation/live_sidepanel/gf-d1314-form-07-target.png`
- `docs/production_validation/live_sidepanel/gf-d1314-pagination-05.json`
- `docs/production_validation/live_sidepanel/gf-d1314-pagination-05-target.png`
- `docs/production_validation/live_sidepanel/gf-d1314-collection-01.json`
- `docs/production_validation/live_sidepanel/gf-d1314-collection-01-target.png`
- `docs/production_validation/live_sidepanel/gf-d1314-collection-02.json`
- `docs/production_validation/live_sidepanel/gf-d1314-collection-02-target.png`
- `docs/production_validation/live_sidepanel/gf-d1314-frame-04.json`
- `docs/production_validation/live_sidepanel/gf-d1314-frame-04-target.png`
- `docs/production_validation/live_sidepanel/gf-d1314-tabs-01.json` (safe failing diagnostic; one navigation, zero duplicate/new-tab side effects)
- `docs/production_validation/live_sidepanel/gf-d1314-tabs-02.json` (safe failing diagnostic; both destinations opened once, focus withheld when exact tab inventory was absent)
- `docs/production_validation/live_sidepanel/gf-d1314-tabs-03.json`
- `docs/production_validation/live_sidepanel/gf-d1314-tabs-03-target.png`

## Remaining before the Days 13–14 exit

- Complete the remaining capability matrix for verified download and production-owned content insertion. Tab lifecycle and same-origin child-frame execution now pass; cross-origin frame isolation remains part of the live safety matrix.
- Run unseen/randomized DOM variants for each mutation family.
- Complete restart/resume and stale-target live variants with duplicate-effect accounting.
- Complete prompt-injection, cross-origin, account-confusion, and privileged-URL live safety cases.
- Validate two structurally different real services for each capability where the action is safe and authorized.

Day 15 and the original upload/send certification remain blocked until this matrix is complete.
