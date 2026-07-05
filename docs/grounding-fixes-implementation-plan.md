# Grounding Fixes — Implementation Plan

**Status:** Implementation plan. No code yet. Scope is frozen to exactly the three **Proven Necessary** items from the Engineering Reality Check's implementation contract — nothing broader.
**Source contract:** the three Fix specs already written (Fix 1: candidate-generation coverage, Fix 2: selector/action-affordance ranking signal, Fix 3: duplicate disambiguation). This document sequences them into small, independently mergeable milestones.

---

## Milestone map (dependency graph)

```
M-G1 (extraction coverage — accordion)         ── independent in code
        │  (sequenced first for validation clarity — see below)
        ▼
M-G2 (ranking: selector/action-affordance)     ── same file as M-G3, different region
        │  (sequenced before M-G3: same function, avoid merge conflicts)
        ▼
M-G3a (ranking: minimal duplicate tie-break, no new data source)
        │  (conditional escalation — only if benchmark proves insufficient)
        ▼
M-G3b (ranking: duplicate disambiguation via content_blocks geometry) — OPTIONAL, gated
```

**Why M-G1 precedes M-G2/M-G3 despite no code dependency:** they touch entirely different files (`extractor_v2.ts`/`injected_scripts.js` vs. `relevance_ranker.py`) and could technically be built in parallel. They are sequenced because a full-suite regression run's *results* are only cleanly attributable if the candidate set feeding the ranker is already known-complete — re-ranking an incomplete extraction (M-G1 unmerged) would confound M-G2/M-G3's own validation. This is a validation-ordering choice, not a compile/merge dependency.

**Why M-G2 precedes M-G3a/3b:** both modify `RelevanceRanker.rank()` — different regions of the same function (M-G2: the term-overlap text pool; M-G3: the tie-break/sort key), landed as sequential commits to avoid merge conflicts in one file, not because either depends on the other's *logic*.

**Why M-G3b is conditional, not committed to now:** per the Reality Check's Part 4 conclusion, the minimal implementation (M-G3a) may already be sufficient using data already captured (`bounding_box`, already present on every `InteractiveElement`). M-G3b (extending `ContentBlock` with geometry, wiring `compressor.py` to pass `content_blocks` into the ranker) is only justified if M-G3a's own benchmark validation proves insufficient — this is a stop-condition-gated milestone, not a default one.

---

## Milestone M-G1 — Candidate Generation coverage

### 1. Exact files to modify
- `extension/src/content/extractor_v2.ts`
- `backend/benchmark/injected_scripts.js`
- `backend/tests/benchmark/test_injection_fidelity.py`

### 2. Exact functions/classes involved
- `extractPageContextV2()` in both `.ts` and `.js` — specifically the `INTERACTIVE_SELECTOR` constant and the `document.querySelectorAll(INTERACTIVE_SELECTOR)` candidacy call inside it. No new function, no new class.

### 3. Dependency order
First. No dependency on any other milestone in this plan.

### 4. Independent of
M-G2, M-G3a, M-G3b entirely — disjoint file set (extension/extractor layer vs. backend ranking layer).

### 5. Benchmark updates required
**None.** `fixture__accordion` already exists in `m0_scenarios.py` and already targets this exact scenario — no new scenario, no new fixture page.

### 6. Existing tests that should change
None require modification — the drift-guard tests (`test_action_cases_match_executor_ts`, `test_extractor_pii_redaction_preserved`, `test_extractor_caps_preserved`) assert properties unrelated to candidacy criteria and should continue to pass unchanged.

### 7. New tests to add
One parity test in `test_injection_fidelity.py`, following the exact pattern already established by M1.2's `test_value_capture_present_in_both_files` — asserting that whatever new candidacy signal is added exists identically in both `extractor_v2.ts` and `injected_scripts.js`.

### 8. How this milestone is validated
- `tsc --noEmit` (extension compiles).
- Drift-guard suite (`pytest tests/benchmark/test_injection_fidelity.py`) — including the new parity test.
- `python -m benchmark.m0_runner --suite nightly --task fixture__accordion --executor playwright` — the single most direct, targeted check.
- A full 27-task regression run before this milestone is considered done (per the general rule that candidacy-criteria changes affect every task's element list, not only accordion-shaped ones).

### 9. Rollback strategy
Revert `extractor_v2.ts` and `injected_scripts.js` together as one paired change (per the drift-guard convention every prior milestone in this project has followed). No schema or wire-format change is implied, so rollback carries no data-migration concern.

### 10. Expected benchmark impact
`fixture__accordion`: `FAILED/GROUNDING` → `COMPLETED`, with the trace showing the real `data-testid="q2"` selector chosen instead of a fabricated one. No other task is expected to change status from this milestone alone — no other currently-observed failure is attributed to a coverage gap.

---

## Milestone M-G2 — Ranking: selector/action-affordance signal

### 1. Exact files to modify
- `backend/app/context_compression/relevance_ranker.py`
- `backend/tests/unit/test_relevance_ranker.py` (new file)

### 2. Exact functions/classes involved
- `RelevanceRanker.rank()` — specifically the `text` term-pool construction line (currently `text = " ".join(... for key in ("text","aria_label","accessibility_name","placeholder","role","type"))`). `RelevanceRanker._terms()` is reused, not modified. No new class.

### 3. Dependency order
Second (after M-G1 merges, per the validation-ordering rationale above). Independent of M-G3a/3b in *logic*; sequenced before them only to avoid two milestones editing the same function concurrently.

### 4. Independent of
M-G1 entirely (disjoint files). Logically independent of M-G3a/3b — a different scoring signal, not a shared code path — but landed as a separate, prior commit in the same file for merge cleanliness.

### 5. Benchmark updates required
**None.** Reuses `amazon_in__product_search_price` and `cross_site__amazon_search_github_compare`, both already defined in `m0_scenarios.py`.

### 6. Existing tests that should change
- `tests/unit/test_v23_enhancements.py::test_compressor_emits_only_planner_contract_and_ranks_relevance` — **must be re-verified, not assumed unaffected.** This test asserts an exact top-ranked selector for a 2-element synthetic case; adding a new scoring signal changes `rank()`'s output for *every* caller, including this one. It should be re-run and only edited if it genuinely regresses — not modified preemptively.
- `tests/unit/test_m11_episodic_memory.py` and `tests/unit/test_m12_observation_completeness.py` — these call `ContextCompressor().compress(...)` with `MagicMock()` page contexts. They do not directly assert on ranking scores, so they are not expected to require changes, but should be re-run as part of this milestone's validation since they exercise the same call path.

### 7. New tests to add
`tests/unit/test_relevance_ranker.py` — a dedicated unit test file (none currently exists) reconstructing the real Amazon scoring scenario using the actual recorded element shapes from the investigation (the unlabeled correct button, the labeled decoy, the already-filled search box), asserting the previously-losing correct element now scores at or above the decoy.

### 8. How this milestone is validated
- The new reconstructed-scoring unit test (item 7) — the narrow, directly-attributable proof.
- Re-run of the three existing tests flagged in item 6.
- `python -m benchmark.m0_runner --suite nightly --task amazon_in__product_search_price --executor playwright` and the same for `cross_site__amazon_search_github_compare` — the broader, less directly-attributable proof (confounded by recovery/reflection, both also active on these tasks).
- A full 27-task regression run, since this signal affects ranking on every task, not only Amazon-shaped ones.

### 9. Rollback strategy
Revert the single term-pool change in `relevance_ranker.py`. No other file is touched by this milestone in isolation, so rollback is a single-function, single-file revert with no cleanup elsewhere.

### 10. Expected benchmark impact
**Narrowly:** the reconstructed scoring test shows the correct button outranking the decoy. **Broadly:** the trace for `amazon_in__product_search_price` and `cross_site__amazon_search_github_compare` shows `#nav-assist-search` no longer selected. Task-level completion is a weaker, confounded claim than the narrow scoring proof — this milestone's primary evidence is the scoring test, not task completion.

---

## Milestone M-G3a — Ranking: minimal duplicate tie-break (no new data source)

### 1. Exact files to modify
- `backend/app/context_compression/relevance_ranker.py`
- `backend/tests/unit/test_relevance_ranker.py` (extends the file created in M-G2)

### 2. Exact functions/classes involved
- `RelevanceRanker.rank()` — specifically the sort key currently `(score, -index)`. The tie-break addition uses only data already present on every candidate today (each `InteractiveElement`'s own `bounding_box`, already captured; no new field, no new extraction).

### 3. Dependency order
Third — after M-G2 merges (same file, sequential to avoid conflicts). Not logically dependent on M-G2's *signal*.

### 4. Independent of
M-G1 entirely. Independent of M-G2 in scope (different region of `rank()`), sequenced only for merge cleanliness.

### 5. Benchmark updates required
**None.** Reuses `amazon_in__add_to_cart`, already defined.

### 6. Existing tests that should change
Same three flagged under M-G2 (item 6) — the sort key change is a second, cumulative modification to the same function's output; all three should be re-verified again after this milestone, not assumed safe on the strength of M-G2's re-verification alone.

### 7. New tests to add
Extends `test_relevance_ranker.py`: a reconstructed add-to-cart scenario — N structurally-identical synthetic candidates (same score) with distinguishing signal available from data already on the candidate record — asserting the tie no longer resolves by index alone.

### 8. How this milestone is validated
- The new tie-break unit test (item 7).
- Re-run of the three flagged existing tests.
- `python -m benchmark.m0_runner --suite nightly --task amazon_in__add_to_cart --executor playwright`.
- Full 27-task regression run (same rationale as M-G1/M-G2 — this touches every task's candidate ordering).

### 9. Rollback strategy
Revert the sort-key change in `relevance_ranker.py`. Single-file revert, no schema change.

### 10. Expected benchmark impact — and the explicit escalation gate to M-G3b
**If sufficient:** `amazon_in__add_to_cart`'s trace shows a single, consistent product targeted across steps (not five different ones), and a materially lower step count before any terminal state. **If insufficient** (the trace still shows the agent interacting with a different product than the task implies, because the data already available on each candidate doesn't actually carry the distinguishing signal needed — e.g., a product title that lives only in `content_blocks`, not on any `InteractiveElement`) — this is the specific, evidence-based trigger for M-G3b. M-G3a's outcome is the sole determinant of whether M-G3b is built at all.

---

## Milestone M-G3b — Ranking: duplicate disambiguation via `content_blocks` geometry (CONDITIONAL — build only if M-G3a's validation proves insufficient)

### 1. Exact files to modify
- `backend/app/schemas/request.py` (`ContentBlock` — add geometry)
- `extension/src/content/extractor_v2.ts` (populate that geometry at extraction)
- `backend/benchmark/injected_scripts.js` (mirror, per the drift-guard convention)
- `backend/app/context_compression/compressor.py` (`ContextCompressor.compress()` — pass `page_context.content_blocks` into the ranker call)
- `backend/app/context_compression/relevance_ranker.py` (`RelevanceRanker.rank()` — accept and use the additional context)
- `backend/tests/benchmark/test_injection_fidelity.py`, `backend/tests/unit/test_relevance_ranker.py`

### 2. Exact functions/classes involved
- `ContentBlock` (Pydantic schema)
- `extractPageContextV2()`'s `collectContentBlocks()` (both `.ts` and `.js`)
- `ContextCompressor.compress()`
- `RelevanceRanker.rank()` — signature change (an additional parameter)

### 3. Dependency order
Only after M-G3a is merged AND M-G3a's own benchmark validation (item 10 above) has produced the "insufficient" result. Not a default next step.

### 4. Independent of
M-G1, M-G2 entirely (disjoint files/logic). Not independent of M-G3a — this milestone's existence is conditioned on M-G3a's measured outcome.

### 5. Benchmark updates required
None — same task (`amazon_in__add_to_cart`), no new scenario.

### 6. Existing tests that should change
`test_v23_enhancements.py::test_compress_without_cognitive_context` and any other test constructing a `PageContext`/`ContentBlock` directly would need to supply the new field if it is non-optional — **the field should be added additively (optional/defaulted)** consistent with every prior schema change in this project (M1.1's `recent_actions`, M1.2's `state` keys), so that existing test fixtures continue to construct valid objects without modification. If any test fails, it indicates the field was not added additively and must be reconsidered before proceeding — not silently patched around.

### 7. New tests to add
- A drift-guard parity test in `test_injection_fidelity.py` for the new `ContentBlock` geometry field, following the established pattern.
- An extension of `test_relevance_ranker.py` covering disambiguation via `content_blocks` proximity specifically.

### 8. How this milestone is validated
Same structure as M-G3a: a narrow reconstructed unit test, `--task amazon_in__add_to_cart` targeted run, full 27-task regression run — plus explicit confirmation that `compressor.py`'s changed call signature does not break any other caller of `compress()` (checked via the full unit suite, not assumed).

### 9. Rollback strategy
Revert all five source files as one paired change (they move together — a partial revert, e.g. reverting `compressor.py` but not `relevance_ranker.py`, would break the call signature). No prior milestone is affected by this revert.

### 10. Expected benchmark impact
Same as M-G3a's stated goal (consistent single-product targeting, lower step count) — this milestone exists only to reach that goal if M-G3a's narrower mechanism could not.

---

## Cross-milestone regression discipline

Every milestone above independently requires a full 27-task regression run, not only its own targeted task — restated here once rather than per-milestone: **M-G1 changes candidacy for every task's element list; M-G2/M-G3a/M-G3b change ranking order for every task's element list.** None of the four milestones has a blast radius confined to the task that motivated it. A milestone is not complete until the full-suite run shows no new regressions relative to the last full-suite baseline, in addition to its own targeted task changing as expected.

## What is explicitly excluded from this plan
Everything classified **Likely Helpful**, **Nice to Have**, or **Not Yet Justified** in the Engineering Reality Check — the full 7-layer pipeline split, the full accessible-name computation algorithm, shadow-DOM/iframe piercing, universal repeated-group/ordinal metadata, and any vision/OCR/learning connection point. None of these four milestones introduces any of them. If implementation of M-G1–M-G3b exposes a concrete contradiction with this plan's assumptions, that is the only condition under which returning to evidence-gathering is warranted — not a default next step.
