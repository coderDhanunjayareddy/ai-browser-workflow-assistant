# M1 Engineering Specification — Reasoning Loop Repair

**Status:** Final design document. No code. This is the implementation contract.
**Supersedes:** nothing architectural — this is additive to the existing loop.
**Built from confirmed evidence:** `docs/` M0.7 (root cause), M0.8 (generalization), M0.9 (reflection capability). Their conclusions are treated as architectural fact and are not re-litigated here.

---

## Part 1 — Problem Statement (three confirmed deficiencies)

### 1. Episodic memory loss

- **Root cause:** the compression layer discards the record of prior actions before the planner reasons.
- **Where:** `app/context_compression/compressor.py:27-33` (`ContextCompressor.compress` copies `verified_facts`, `active_goal`, `relevant_elements`, `important_failures`, `task_constraints` into the result dict — it computes `state["completed_nodes"]` and `state["pending_nodes"]` in `StateSummarizer.summarize` but never copies them in); `app/context_compression/state_summarizer.py:16-19` (a step is filed into `completed` when `execution_result == "success"`, and only `failures` is exported); `app/services/ai_service.py:604-616` (when `compressed_context is not None`, the `build_user_message(...)` branch — which *would* render `prior_steps_text` — is never taken; the transmitted message is `"COMPRESSED PLANNER CONTEXT:\n" + json.dumps(compressed_context)`).
- **Evidence:** M0.7 Parts 1–3 (code-line trace); M0.7 Part 2 (Step-1/Step-2 prompts differ only in a constant field); M0.8 Task 1 (identical mechanism confirmed across `fixture__pagination`, `fixture__login_form`, `fixture__modal_dialog`).
- **Why it affects real sites too:** the discarding happens in the **shared** `compress()` → `/analyze` path used by every multi-step task regardless of website (M0.8 Task 3). MakeMyTrip's multi-field form, Amazon's search→open→cart, Gmail's open→read all route through the same `ContextCompressor`.

### 2. Observation incompleteness

- **Root cause:** the DOM snapshot never reports the *current value/state* of a control — only its static identity (role, label, placeholder).
- **Where:** `extension/src/content/extractor_v2.ts` — the element-mapping block (`item.input_type`, `item.placeholder`) never reads `.value`, `.checked`, `.selected`, or ARIA `aria-expanded`/`aria-checked` into a value the model can use to know "this is already filled/checked/expanded." The Pydantic mirror `InteractiveElement` ([app/schemas/request.py:5-17](backend/app/schemas/request.py:5)) has a `state: dict` field that is populated only for `aria-expanded`/`aria-checked`/`disabled`/`readonly` ([extractor_v2.ts:104-117]) — never for the actual current value.
- **Evidence:** M0.7 Part 1 (observe-stage table: "no input `.value`" listed as a discard); M0.8 Task 1 (login fixture: "field looks empty every step even if history were present" — an *independent* cause from #1, confirmed by the fact that restoring history alone is necessary-but-maybe-insufficient for form tasks).
- **Why it affects real sites too:** every login form, checkout form, and multi-field search (MakeMyTrip, Amazon quantity/options, LinkedIn filters) depends on the model knowing what it already typed/selected. This is a property of `extractor_v2`, not of any one site.

### 3. Missing reflection capability

- **Root cause:** no component between "planner input assembled" and "action selected" ever compares the proposed action to what was already attempted, or decides "this approach isn't working, try differently." The single LLM call is the entire reasoning step; nothing wraps it with a check-and-revise step.
- **Where:** `app/orchestrator/workflow_orchestrator.py:89-106` calls `ai_service.analyze(...)` once and returns its result directly — no deliberation loop, no second pass, no veto. `app/services/ai_service.py` — zero occurrences of any reflection/recovery/exploration term (M0.9 Task 2, exhaustive repo grep). The only near-matches (`execution_gateway/browser/{recovery,adaptive_resolver}`, `exploration/*`, `failure_engine/*`) are deterministic, locator-level, and structurally unreachable from `/analyze` (orphaned back-half, per the ARP/alignment docs).
- **Evidence:** M0.9 Task 1 (memory alone doesn't force a strategy change — `#p2` stays top-ranked regardless); M0.9 Task 3 (prompt has no "avoid repeating a no-progress action" instruction, and the one line that mentions "prior steps" is inert on the compressed branch); M0.9 Task 4 (5 concrete scenarios where memory-with-no-reflection still repeats); M0.9 Task 5 conclusion **B**.
- **Why it affects real sites too:** reflection is a property of the reasoning step itself, invoked identically for every task/site — it is not a per-site behavior.

---

## Part 2 — Architectural Principles (binding constraints for Part 4 onward)

Every design choice below was screened against this checklist before inclusion. Where a principle forced rejecting an option, that is noted explicitly in Part 4/6.

| Principle | How M1 satisfies it |
|---|---|
| Preserve current architecture | No new stage is inserted into the canonical loop; reflection is a sub-step *inside* Reasoning, not a new pipeline stage |
| Preserve the browser extension | `extractor_v2.ts`/`executor_v2.ts` gain additive fields only; no removed/renamed field; extension ships unmodified until it opts in |
| Preserve benchmark compatibility | `benchmark/` reads the same `AnalyzeResponse`; new optional fields are additive; existing 74+22+35 offline tests remain valid |
| Preserve existing APIs | `POST /analyze` request/response shape is unchanged at the wire level for any caller that doesn't send the new optional fields |
| Preserve `AnalyzeResponse` | Zero fields removed; at most one new **optional** field considered (see Part 5) |
| Preserve Prompt Builder structure | `build_user_message()` signature unchanged; the compressed-context *content* gains keys, the *builder function* is not touched |
| Preserve backward compatibility | Every new field has a default; old callers (extension not yet updated, old benchmark runs) work unmodified |
| No new platform layer | Reflection is realized within the existing `/analyze` reasoning boundary, not a subsystem with its own models/registry/routes — the exact mechanism is an implementation-time decision made after M1.1/M1.2 are benchmarked (Part 6) |
| No parallel planner | One planner call remains the single source of the next action; reflection *informs* that call, it does not add a second competing planner |
| No duplicated state | Episodic memory is realized as *previously-discarded fields already computed by `StateSummarizer`*, not a new store |
| No special-case website logic | All changes are in `extractor_v2`, `compressor.py`, `state_summarizer.py`, `ai_service.py` — none reference any site name |
| No hardcoded benchmark behavior | The benchmark's own recording (`m0_task_runner.py`) gets the same treatment as the extension — same `PriorStep.execution_result` semantics for both |

---

## Part 3 — M1 Scope (explicit classification)

| Feature | Status | Notes |
|---|---|---|
| **Episodic memory** (surface completed actions) | **Included** | `compress()` gains a `recent_actions` key sourced from the already-computed `completed_nodes` |
| **Reflection** (structured self-check before acting) | **Included, mechanism deferred** | A bounded capability that detects and avoids repeating no-progress actions; the specific mechanism (extended primary pass, bounded secondary call, or other) is chosen after M1.1/M1.2 are implemented and benchmarked — see Part 6 |
| **Observation completeness** (values/checked/selected/expanded) | **Included** | `extractor_v2.ts` + `InteractiveElement.state` gain fields; see Part 7 |
| **Progress tracking** (dom_changed signal reaching the planner) | **Included, as neutral info only** | Never a success/failure verdict (M0.8 caveat on Option B) — see Part 5 |
| **Retry behavior** | **Excluded** | Retry/recovery policy in the benchmark (`retry_budget`) and any future execution-gateway wiring is untouched; M1 changes *what the planner knows*, not retry mechanics |
| **Prompt updates** | **Included, minimal** | One new section describing `recent_actions`; SYSTEM_PROMPT numbered rules otherwise untouched |
| **Compression changes** | **Included** | `compressor.py` + `state_summarizer.py` — additive keys only |
| **Working memory** (`verified_facts` / `state_engine`) | **Deferred** | Populating `verified_facts` from benchmark runs is a real gap (M0.7 Part 3, item 6) but is a *separate* mechanism from episodic action memory; out of M1 to keep scope bounded |
| **State engine** (`app/state_engine/*`) | **Deferred** | No schema or behavior change; already receives writes only in the live `/analyze`+`/workflow` path, unaffected here |
| **Benchmark updates** | **Included, mechanical only** | `m0_task_runner.py` must stop recording a no-op as bare `"success"` and instead pass a progress-qualified `execution_result` — mechanical propagation of an existing local computation (`dom_changed`), not new benchmark logic |
| **Trace viewer updates** | **Included, additive display only** | Surface the new `recent_actions`/reflection fields in the existing viewer sections; no new viewer architecture |
| **Extension updates** | **Included, additive only** | `extractor_v2.ts` gains value/checked/selected/expanded capture; `executor_v2.ts` unchanged (it already reports execution success/failure; no new responsibility) |

Nothing here is deferred to "later in M1" — every row is either **Included** (with the exact boundary stated) or explicitly **Excluded/Deferred** to a future milestone.

---

## Part 4 — Detailed Design

### 4.1 Episodic memory restoration

- **Why it exists:** without it, every successful action is invisible to the next reasoning step (Part 1 §1).
- **Owning subsystem:** `context_compression` (it already computes the data; it just needs to stop dropping it).
- **Integrates into:** `ContextCompressor.compress()` → `compressed_context` dict → `ai_service.analyze()`'s compressed branch (already the live code path — no new branch created).
- **Files expected to change:**
  - `backend/app/context_compression/state_summarizer.py` — `summarize()` continues to return `completed_nodes`/`pending_nodes` (already does); no signature change.
  - `backend/app/context_compression/compressor.py` — `compress()` result dict gains one new key, `recent_actions`, populated from `state["completed_nodes"]` **with the selector preserved** (currently `completed_nodes` is a list of description strings only — losing the selector was itself a minor, second-order loss worth closing at the same time since it's the same edit).
  - `backend/app/services/ai_service.py` — no change required; the compressed dict is serialized wholesale via `json.dumps(compressed_context)`, so a new key is transmitted automatically once `compress()` emits it.
- **Public interfaces:** `POST /analyze` wire contract unchanged (the new key lives *inside* the opaque `"COMPRESSED PLANNER CONTEXT: {...}"` string the model receives, not in any Pydantic response field).
- **Internal interfaces:** `ContextCompressor.compress(...) -> dict` — return type unchanged (still `dict`), one additive key.
- **Data flow before:** `prior_steps` → `StateSummarizer.summarize()` computes `completed`/`failures` → `compress()` copies only `important_failures` → planner sees only failures.
- **Data flow after:** `prior_steps` → `StateSummarizer.summarize()` (unchanged) → `compress()` copies `important_failures` **and** `recent_actions` (from `completed`, selector-qualified) → planner sees both what failed and what it already did.

### 4.2 Reflection capability

Specified as a capability, not a fixed mechanism — see Part 6. No specific implementation (extended primary pass vs. bounded secondary call vs. other) is committed to here; that choice is made after M1.1 and M1.2 are implemented and benchmarked.

### 4.3 Observation completeness

- **Why it exists:** the planner cannot reason about "already filled" if the field always reads as empty (Part 1 §2).
- **Owning subsystem:** the extraction layer — `extension/src/content/extractor_v2.ts` (live path) and, for the benchmark's Mode-B fidelity mirror, `backend/benchmark/injected_scripts.js` (verbatim port, per the existing drift-guard convention in `tests/benchmark/test_injection_fidelity.py`).
- **Integrates into:** the existing `InteractiveElement.state: dict` field — already present, already schema-compatible, currently populated only for `expanded`/`checked`/`disabled`/`readonly` derived from ARIA attributes. No new field is added to the Pydantic model; `state` gains new *keys*.
- **Files expected to change:**
  - `extension/src/content/extractor_v2.ts` — the element-mapping block additionally reads `.value` (inputs/textareas/contenteditable text), `.checked` (checkbox/radio), `.selectedOptions`/`.value` (select), and existing `aria-expanded` handling is extended to summary/details and any `[aria-expanded]` element, not just those already queried.
  - `backend/benchmark/injected_scripts.js` — the mirrored port gains the identical logic (drift-guard test already enforces this stays in sync).
  - `backend/app/services/context_service.py` — `format_page_context()`'s per-element rendering line (`meta` list construction) gains one conditional: if `el.state` contains a current value/checked/selected marker, render it inline (e.g. `value="tester"` or `checked=true`) so it reaches the *uncompressed* prompt path too (used by `/assist` and non-benchmark callers) — additive to existing formatting, no removed fields.
  - `backend/app/context_compression/relevance_ranker.py` — no change required; ranking already passes through arbitrary `data` dict keys via `item.model_dump()`, so `state` values ride along unchanged.
- **Public interfaces:** `PageContext`/`InteractiveElement` Pydantic schema — **zero field additions or removals**; `state: dict` already accepts arbitrary keys.
- **Internal interfaces:** none new; existing `isVisible`/`getAccessibilityState`-style helpers in `extractor_v2.ts` gain more populated keys.
- **Data flow before:** DOM element → `{role, text, aria_label, state:{expanded?,checked?,disabled?,readonly?}}` → model sees identity, not current content.
- **Data flow after:** DOM element → `{..., state:{...existing keys..., value?, selected_option?, checked?}}` → model can distinguish "empty field" from "already filled field."

---

## Part 5 — Data Model Changes

| Object | Existing fields | New fields | Removed fields | Compatibility strategy | Migration |
|---|---|---|---|---|---|
| `CompressedContext` (the dict from `ContextCompressor.compress`) | `verified_facts, active_goal, relevant_elements, important_failures, task_constraints`, optional `cognitive_context` | `recent_actions: list[{description, selector, action_type, value, page_changed: bool\|null}]` | none | it is an internal `dict`, not a Pydantic model exposed over the wire — adding a key cannot break any external contract; consumers (`ai_service`) already `json.dumps` the whole dict | none needed — first read of the new key is the same code path that reads any other key |
| `PriorStep` (Pydantic, `app/schemas/request.py:38`) | `action_type, description, target_selector, value, execution_result, page_analysis, page_url, page_title, page_metadata` | none (see below) | none | `execution_result` remains a free-form `str`; instead of a schema change, callers (extension, benchmark) are asked to write a **richer string value** into the existing field, e.g. `"success (page unchanged)"` vs `"success"` — a value-convention change, not a schema change | no migration: old callers sending bare `"success"` still parse; `StateSummarizer`'s `.lower().startswith("success"...)` check still matches |
| `InteractiveElement` (Pydantic, `app/schemas/request.py:5`) | `type, text, selector, visible, input_type, placeholder, role, aria_label, accessibility_name, state: dict, bounding_box, element_id` | none (schema-level) — `state` dict gains **keys**: `value`, `checked`, `selected`, `expanded` (already existed) | none | `state: dict` has no fixed key set today — Pydantic accepts any JSON object; adding keys is invisible to existing readers that don't look for them | none needed |
| `StateSummary` (return of `StateSummarizer.summarize`) | `verified_facts, active_goal, completed_nodes, pending_nodes, important_failures` | `completed_nodes` entries change shape: currently `list[str]` (description only) → `list[{description, selector, action_type, value}]` | none removed, but this is a **shape change within an already-internal, non-API type** | this dict is never serialized to a client; it is consumed only by `compress()` in the same request. Because both are edited together, there is no external compatibility surface to preserve | none needed — internal to one call |
| `AnalyzeResponse` / `SuggestedAction` (Pydantic, `app/schemas/response.py`) | unchanged fields | **none** | none | Part 2 principle: preserve `AnalyzeResponse` exactly. Reflection's output (see Part 6) is folded into the existing `reasoning` string field of `SuggestedAction`, not a new field, and `analysis` continues to hold the free-text explanation | not applicable |
| `ExecutionRecord` (benchmark `M0StepRecord`/`M0TaskResult`) | unchanged fields (validation_detail, execution_success, etc.) | none required for M1 | none | the benchmark's `m0_task_runner.py` already computes `dom_changed`; M1 only changes **what string it writes into `prior_steps[-1]["execution_result"]`** — a call-site change, not a model change | none |

**No schema migration is required anywhere.** Every change is additive-within-an-existing-flexible-field (`state: dict`, `execution_result: str`) or additive-key-in-an-internal-dict (`CompressedContext`). This was a deliberate design constraint, not a coincidence — it is how "preserve existing APIs / no schema breakage" is satisfied while still closing the evidence-backed gaps.

---

## Part 6 — Reflection Design (capability specification; mechanism deferred)

**Framing.** M0.9 proved that reflection — recognizing "I already tried this and it produced no progress; I should choose differently" — does not exist anywhere in the live architecture (Part 1 §3). It did **not** prove that reflection must be built as a second LLM call, or fix any other implementation mechanism. This section specifies what reflection **must achieve** architecturally. It deliberately does **not** commit to *how* it is realized.

The mechanism — extending the primary reasoning pass with reflection-aware input, adding a bounded secondary call gated on a trigger condition, or another approach entirely — is an **implementation-time decision made after M1.1 (episodic memory) and M1.2 (observation completeness) are implemented and benchmarked** (Part 10, M1.3). Those two changes may substantially reduce the class of failures reflection needs to handle, and the benchmark evidence at that point is the correct basis for choosing the cheapest mechanism that still meets the guarantees below.

### Purpose
Detect when the action about to be produced is a repeat of a recent action that produced no verified progress, and, when detected, cause a different action to be produced instead — or, if repetition is genuinely still correct, make that an explicit, inspectable claim rather than a silent repeat.

### Inputs
- The candidate action that would otherwise be returned for this step.
- The episodic memory available via `compressed_context.recent_actions` (Part 4.1) — action type, selector, and page-changed signal for recently attempted actions.
- The current page observation (already available to Planning; Part 4.3 makes it more complete).

### Outputs
- A `SuggestedAction`, expressed entirely through the existing `AnalyzeResponse`/`SuggestedAction` schema (Part 5) — no new field, regardless of mechanism. If reflection changes the action, `reasoning` explains what was abandoned and why. If it concludes repetition is still correct, `reasoning` states that explicitly.

### Guarantees (binding regardless of mechanism)
- **Bounded:** reflection adds at most a small, fixed amount of additional reasoning work per `/analyze` call — never an open-ended or recursive self-argument loop.
- **Fails safe:** if reflection cannot produce a confident alternative, the caller still receives a valid `SuggestedAction` — reflection is a best-effort enhancement, never a hard dependency of the response.
- **No parallel planner:** exactly one action is returned per call; reflection informs which action that is, it does not add a second, independently-authoritative planning path.
- **No new platform layer:** whatever form it takes, reflection is realized within the existing single reasoning boundary of `/analyze` — no new models, registry, persistence, or route.
- **Backward compatible:** callers unaware of reflection (old benchmark runs, extension builds that haven't adopted `recent_actions`) receive the same `AnalyzeResponse` shape and continue to function unmodified.
- **No cost regression on the non-triggered path:** a task whose planner never repeats an action costs the same, in calls and latency, as it did before reflection existed — whatever mechanism is chosen.
- **Measurable only through the benchmark:** reflection's presence and effect are verified by re-running the fixture regression set (`fixture__pagination`, `fixture__login_form`, `fixture__modal_dialog`) and any real-site multi-step sample, and observing a reduction in STUCK/PLANNING outcomes relative to the M1.1+M1.2 baseline — not by inspecting internal call counts alone.

### Trigger condition
Reflection is warranted, at minimum, when the candidate action's `(action_type, target_selector)` matches an entry in `recent_actions` (Part 4.1) whose `page_changed` is `false` or unknown. This is the same structural signal already available once M1.1 lands. *Where* in the pipeline this condition is evaluated, and whether it gates an additional call or simply shapes what is fed into a single call, is part of the mechanism decision — not fixed here.

### Constraints
- No site-specific logic — a generic action/selector repeat check, never a per-site rule.
- No dependency on any subsystem outside the existing `/analyze` request/response boundary — no new persistence, no new service.
- Must remain inspectable via the trace layer regardless of mechanism (see Compatibility below).
- Must not alter cost/latency on tasks where no repeat occurs.

### Compatibility requirements
- `AnalyzeRequest`/`AnalyzeResponse`/`PriorStep`/`InteractiveElement` schemas: unchanged (Part 5), under any mechanism.
- Trace schema (`planner_trace_v1`, `docs/trace-observability.md`): reflection's additional reasoning content must be representable within the existing per-step trace structure under either candidate shape — as an additional `provider_request`/`provider_response` pair attributable to the same `step_index` if the mechanism performs an extra call (the schema already supports this as a list-friendly extension point), or directly within the existing pair's fields if the mechanism instead extends the single call. Either way, no schema version bump is required.
- Benchmark: `m0_task_runner.py` and `TraceRecorder` require no change to accommodate reflection under any candidate mechanism, because both already treat one step's planner interaction generically.

### Reflection vs. Planning vs. Execution vs. Validation

| Stage | Question it answers | Who performs it | Where |
|---|---|---|---|
| **Planning** | "What action should I take next, given the current page and goal?" | LLM reasoning | `ai_service.analyze()` (unchanged) |
| **Reflection** | "Is the action about to be taken one that already failed to make progress, and if so, what should change?" | LLM reasoning; mechanism determined in M1.3 (Part 10) after M1.1/M1.2 evidence | within the existing `/analyze` reasoning boundary — exact form deferred |
| **Execution** | "Perform this specific action against the real page." | Executor (extension `executor_v2.ts` / benchmark `PlaywrightDriver`) | unchanged, outside reasoning entirely |
| **Validation** | "Did the page change / were the success criteria met?" | Deterministic check against DOM/URL/criteria | unchanged (extension approval flow / benchmark `m0_task_runner.py`) |

Reflection sits strictly between Planning and Execution and never touches Execution or Validation code, under any candidate mechanism.

### Benchmark expectations
Reflection's necessity and design are evidence-driven, not assumed. After M1.1 and M1.2 land and are benchmarked, the residual STUCK/PLANNING rate on the fixture regression set (and any available real-site multi-step sample) is the basis for (a) confirming a meaningful share of failures still require reflection, and (b) selecting the mechanism whose cost (implementation complexity, latency, provider spend) is justified by that residual rate. This ordering — implement and measure M1.1/M1.2 first, decide the reflection mechanism second — is itself part of this specification, not a deferral of the requirement.

---

## Part 7 — Observation Improvements

| Control type | Current extraction | M1 addition | Where |
|---|---|---|---|
| Text input / textarea | `input_type`, `placeholder` | `state.value` = current `.value` (redacted through the existing `sanitizeText` SSN/card pattern already in `extractor_v2.ts`) | `extractor_v2.ts` element-mapping block |
| Checkbox | `role="checkbox"` (from `getAccessibilityRole`) | `state.checked` = `.checked` boolean | same block |
| Radio button | `role="radio"` | `state.checked` = `.checked` boolean | same block |
| `<select>` (dropdown) | `role="combobox"` | `state.value` / `state.selected_text` = currently selected option's value/label | same block |
| Editable content (`[contenteditable]`) | already in `INTERACTIVE_SELECTOR` list | `state.value` = current `.textContent` (capped like other text fields) | same block |
| Dynamic text (post-render content) | re-extracted every observation already (fresh DOM each step — this was never the problem, see M0.7 Part 1) | no change needed — freshness was already proven fine | n/a |
| Hidden state (e.g. a dialog that is present but `display:none`) | `isVisible()` filter already excludes non-visible elements from the interactive list entirely | unchanged — hidden elements correctly stay excluded; this is existing correct behavior, not a gap identified in M0.7–M0.9 | n/a |
| Expanded state (accordion/dropdown open) | `state.expanded` already read from `aria-expanded` **only when present as an attribute** | extend the same read to cover native `<details open>` (already partially handled) and elements toggled via class rather than ARIA — **only if** such a case is evidence-backed from a real trace; otherwise this remains an ARIA-attribute read, unchanged in mechanism, just applied more broadly | same block |

All additions are read-only DOM inspection identical in spirit to the calls already present (`el.getAttribute(...)`, `el.checked`, `el.value`) — no new capability class, no new permission, no execution-side change.

---

## Part 8 — Compatibility Analysis

| Surface | Compatibility argument |
|---|---|
| **Browser Extension** | `extractor_v2.ts` changes are purely additive reads into an already-flexible `state` object; `executor_v2.ts` is untouched (Part 3). An extension build that has *not* picked up the extractor change still produces valid `PageContext` — it simply omits the new `state` keys, which the backend already treats as optional (no required-field validation on `state`'s contents). |
| **Benchmark** | `m0_task_runner.py`'s only required change is the *string value* it writes into `PriorStep.execution_result` (Part 5) — a call-site edit, not a schema change. The 74 existing pytest + 22 trace-validation + 35 M0-validation checks assert on `M0TaskResult`/`M0StepRecord`/report shapes, none of which change. `injected_scripts.js` gains the extractor parity fields under the existing drift-guard test, which already enforces sync with the `.ts` source — the test's assertions (action-case parity, fill event order) are unaffected by additive extraction fields. |
| **Trace Framework** | `planner_trace_v1` schema (Part 2 of `docs/trace-observability.md`) is additive-only by its own versioning rule ("never remove or repurpose a v1 key; only add optional keys"). `recent_actions` and any additional reflection reasoning content can be surfaced under the existing `planner_input`/`provider_request`/`provider_response` sections without a schema version bump, regardless of which reflection mechanism M1.3 ultimately selects (Part 6): an additional provider call is simply an additional `provider_request`/`provider_response` pair attributable to the same `step_index` (already a list-friendly extension point); an extended single call surfaces its reasoning directly within that pair's existing fields. Either way, no schema change is required. |
| **Existing Tests** | No Pydantic field is removed or retyped; `StateSummarizer.summarize()` keeps its exact signature and existing return keys (only the *content* of `completed_nodes` gains structure, and that dict is internal, consumed only within the same request — see Part 5). Existing unit tests asserting on `important_failures` behavior are unaffected since that key and its population logic are untouched. |
| **Playwright Adapter** (`execution_gateway/browser/playwright_adapter.py`) | Not touched by M1 at all — M1 changes only the live `/analyze` compressed-context path and the extension/benchmark extractors; the server-side gateway adapter is orthogonal (and already orphaned per the architecture docs). |
| **Gateway** (`execution_gateway/*`) | Not touched — M1 has no dependency on or interaction with the gateway/back-half subsystems (consistent with "no new platform layer"). |
| **Compression** (`context_compression/*`) | This *is* the subsystem being extended — compatibility here means: `ContextCompressor.compress()` keeps its exact keyword-argument signature; only the returned dict's key set grows. Any code that does `compressed_context["important_failures"]` today continues to work unchanged. |
| **Current REST APIs** | `POST /analyze` request/response Pydantic models are byte-identical at the schema level (Part 5). The only wire-visible change is *content* inside the free-text `analysis`/`reasoning` strings (which are already unstructured prose) and richer values inside already-`dict`-typed fields (`state`) and already-`str`-typed fields (`execution_result`). No client that validates against the current OpenAPI schema will see a breaking change. |

**No breaking change exists in this specification.** Every extension point chosen in Parts 4–7 was selected specifically because it is additive within an already-untyped or already-optional container.

---

## Part 9 — Risks

| Change | Technical risk | Regression risk | Perf impact | Memory impact | Complexity | Testability |
|---|---|---|---|---|---|---|
| 4.1 Episodic memory (`recent_actions`) | **Low** — pure data plumbing of already-computed values | **Low** — additive key; existing consumers unaffected | **Negligible** — a few extra small strings in an already-small compressed payload | **Negligible** — bounded by existing 10-step window in `StateSummarizer` | **Low** | **High** — pure function, easily unit-tested with fixed input/output dicts |
| 4.3 Observation completeness | **Low-Medium** — must not leak sensitive values (passwords); requires reusing/extending the existing `sanitizeText` redaction, and password-type inputs must be explicitly excluded from `state.value` capture | **Low** — additive `state` keys | **Negligible** — same DOM read pass, marginally more property reads per element | **Negligible** | **Low-Medium** (the password-exclusion rule needs care) | **High** — deterministic DOM behavior, straightforward fixture-based unit tests |
| 6. Reflection capability (mechanism chosen in M1.3) | **Medium** — depends on LLM reasoning behaving sensibly given the trigger signal; not deterministic, regardless of mechanism | **Low-Medium** — bounded by the Part 6 guarantees (fails safe, no parallel planner), with fallback to the original action on any failure to reflect — cannot make a working flow worse, can only fail to help | **Low–Medium** — cost depends on the mechanism chosen: negligible if the primary pass is extended, up to ~2x on the triggered subset if an additional call is used; either way bounded to steps where the trigger condition fires, never the common path | **Negligible** | **Medium** — the trigger-detection logic and the bounded-invocation guarantee need careful, explicit unit tests regardless of mechanism | **Medium** — validated via the benchmark's `FakeAnalyzeClient` test double scripted to a repeat-then-different-action sequence; exact test shape depends on the mechanism chosen in M1.3 (Part 10) |
| Prompt update (recent_actions section) | **Low** — additive prompt text, same numbered-rule style already in `SYSTEM_PROMPT` | **Low** — does not remove or renumber existing rules | **Negligible** (prompt is already large; a few more lines are immaterial to token cost) | n/a | **Low** | **Medium** — prompt-level behavior is inherently harder to unit-test; validated primarily via the benchmark (Part 11) |
| Benchmark `execution_result` string change | **Low** | **Low** — `StateSummarizer`'s `.startswith("success"...)` matcher still matches a string like `"success (page unchanged)"`... **must verify:** actually it does NOT start with "success" if phrased differently — **this is flagged as an explicit implementation-time check**, not resolved here (see Part 13 note) | n/a | n/a | **Low** | **High** — exactly the kind of thing the existing 74 pytest can pin down before merge |

**Overall ranking, highest→lowest combined risk:** Reflection capability (mechanism TBD) > Observation completeness (password redaction correctness) > Benchmark execution_result wording > Episodic memory > Prompt update.

---

## Part 10 — Implementation Plan

Each milestone is independently mergeable and independently benchmarkable. Order matters: M1.1 (memory) and M1.2 (observation) must land and be benchmarked before M1.3 (reflection) begins — (a) reflection's trigger condition depends on `recent_actions` existing, and (b) the M1.3 mechanism itself is chosen using the benchmark evidence M1.1/M1.2 produce (Part 6).

### M1.1 — Restore episodic memory
- **Objective:** `compress()` emits `recent_actions`; planner can see what it already did.
- **Files:** `context_compression/state_summarizer.py`, `context_compression/compressor.py`.
- **Complexity:** Low.
- **Verification:** unit test asserting `compress()` output contains a `recent_actions` entry for a successful prior step, with selector preserved.
- **Benchmark expected to improve:** STUCK/PLANNING category on `fixture__pagination`, `fixture__login_form`, `fixture__modal_dialog`, and any multi-step real-site task (per M0.8 Task 4 categories).
- **Rollback:** revert the two files; `compressed_context` reverts to its current 5-key shape; no data migration needed since the key was purely additive.

### M1.2 — Observation completeness
- **Objective:** `state` carries current value/checked/selected for form controls; passwords excluded.
- **Files:** `extension/src/content/extractor_v2.ts`, `backend/benchmark/injected_scripts.js` (kept in sync per drift-guard), `backend/app/services/context_service.py` (render `state` values in the uncompressed formatter too, for `/assist` parity).
- **Complexity:** Low-Medium (password-exclusion rule).
- **Verification:** the existing `tests/benchmark/test_injection_fidelity.py` drift-guard, extended to also assert value/checked capture is present in both files identically; a benchmark fixture-level check that a filled field's `state.value` appears in the next observation.
- **Benchmark expected to improve:** login/registration/multi-field form tasks where the observation previously contradicted history (`fixture__login_form`, `fixture__multistep_form`, `makemytrip_com__flight_search`, `docs_google_com__create_type` partially).
- **Rollback:** revert the extractor changes; `state` reverts to its current key set; fully backward compatible either direction.

### M1.3 — Reflection capability (mechanism chosen after M1.1/M1.2 evaluation)
- **Objective:** implement the architectural reflection capability specified in Part 6 — detect and avoid repeating a recent no-progress action — using whichever mechanism the M1.1/M1.2 benchmark evidence justifies. M1.3 begins with an evaluation step, not a fixed implementation:
  1. **Evaluate:** re-run the fixture regression set (and any available real-site multi-step sample) on top of M1.1+M1.2 and measure the residual STUCK/PLANNING rate.
  2. **Choose:** select the cheapest mechanism that plausibly closes the residual gap — candidates include, but are not limited to, extending the primary reasoning pass now that `recent_actions` is richer, or a bounded secondary call gated on the Part 6 trigger condition. The choice is recorded as an explicit decision note alongside this milestone, not assumed in advance.
  3. **Implement** the chosen mechanism against the guarantees and constraints in Part 6.
- **Files:** determined by the mechanism chosen in step 2; every candidate mechanism considered confines its changes to `backend/app/services/ai_service.py` and/or `backend/app/orchestrator/workflow_orchestrator.py` — no other subsystem is touched under any candidate.
- **Complexity:** Medium (evaluation + implementation); the implementation step's complexity varies by the mechanism chosen (Part 9).
- **Verification:** regardless of mechanism — a unit test using the benchmark's existing `FakeAnalyzeClient` pattern asserting that a scripted repeat-of-a-no-progress-action scenario results in a different action (or an explicit repeat justification) being returned; a second test asserting the non-triggered path incurs no additional cost/latency (Part 6 guarantee), with the exact assertion shape adapted to the chosen mechanism.
- **Benchmark expected to improve:** cases where M1.1+M1.2 alone still repeat a *different* dead control or ineffective action (M0.9 Task 4, scenario 3 and others) — expect a reduction in STUCK specifically, measured against the M1.1+M1.2 baseline.
- **Rollback:** whichever mechanism is chosen, it must be revertible by isolating it behind a single conditional or call-site change (not a new settings subsystem), reverting to pre-M1.3 behavior.

### M1.4 — Prompt clarification (reinforcement, not the fix)
- **Objective:** one additive section in `SYSTEM_PROMPT` telling the model to consult `recent_actions` before proposing a repeat.
- **Files:** `backend/app/services/ai_service.py` (`SYSTEM_PROMPT` constant only).
- **Complexity:** Low.
- **Verification:** no unit test possible for prompt wording itself; validated only via benchmark (Part 11).
- **Benchmark expected to improve:** marginal — this is reinforcement per M0.9's conclusion that data must exist before prompting helps; it is sequenced *after* M1.1 for that reason.
- **Rollback:** revert the prompt string.

### M1.5 — Benchmark propagation
- **Objective:** the benchmark writes a progress-qualified `execution_result` string (using the already-computed `dom_changed`) instead of bare `"success"`, so the benchmark's own recorded history matches what M1.1 now surfaces.
- **Files:** `backend/benchmark/m0_task_runner.py` (the `prior_steps.append(...)` call site only).
- **Complexity:** Low, **but see the flagged wording-compatibility check in Part 9** — must confirm the new string still satisfies `StateSummarizer`'s existing success/failure classification, or that classification is intentionally adjusted as part of this same milestone (both are in-scope for M1.5; the exact string format is an implementation-time decision, not re-opened here).
- **Verification:** existing benchmark pytest suite (`tests/benchmark/test_m0_runner_loop.py`) extended with a case asserting the new wording round-trips correctly through `StateSummarizer`.
- **Benchmark expected to improve:** this milestone is what makes M1.1's benefit observable *in the benchmark specifically* (the benchmark is also a caller of `/analyze`, so it must adopt the same convention it is evidence for).
- **Rollback:** revert the one call site.

---

## Part 11 — Validation Strategy

| Milestone | Unit tests | Integration tests | Benchmark | Trace verification | Regression tests |
|---|---|---|---|---|---|
| M1.1 | `compress()` output contains `recent_actions` with selector | full `/analyze` call (mocked provider) confirms the compressed payload transmitted to the provider includes `recent_actions` | re-run `fixture__pagination`/`fixture__login_form`/`fixture__modal_dialog` self-test; compare STUCK rate to the pre-M1.1 baseline captured in the M0.6/M0.7 traces | open a fresh `--trace` run's `viewer.html`; confirm `provider_request.assembled_prompt` now includes the prior click | full existing `tests/benchmark` suite (74+22+35 checks) must still pass unmodified |
| M1.2 | extractor unit test (or a headless DOM fixture) asserting `state.value` appears for a filled input and is absent/redacted for `type="password"` | drift-guard test extended to assert extractor/`injected_scripts.js` parity on the new fields | re-run `fixture__login_form`, `fixture__multistep_form` | trace `observation.elements_summary` shows the filled value | full existing suite must still pass |
| M1.3 | unit test with scripted fake provider: repeat→reflect→different action; and no-trigger→unchanged-cost path (assertion shape adapted to the mechanism chosen per Part 10) | one exercise using the benchmark's existing `FakeAnalyzeClient` double, scripted to a repeat sequence | re-run the three fixtures again on top of M1.1+M1.2; measure STUCK rate reduction *beyond* what M1.1+M1.2 alone achieve | trace shows the additional reasoning that led to a different action for the reflected step — as a second `provider_request`/`provider_response` pair if the chosen mechanism uses an additional call, or within the existing pair's `reasoning` if it extends the primary pass | full existing suite must still pass; explicitly assert the non-triggered path's cost/latency is unchanged from the M1.1+M1.2 baseline |
| M1.4 | none (prompt text) | none | full nightly suite re-run; compare against M1.1–M1.3 baseline | n/a | full existing suite |
| M1.5 | `StateSummarizer` round-trip test with the new wording | `m0_task_runner` step producing the new `execution_result` string, consumed correctly by a real `/analyze` mock | full nightly suite | trace `planner_input.prior_steps_sent` shows the qualified string | existing `test_m0_runner_loop.py` suite |

**Success is always measured using the benchmark**, per the instruction: after each milestone, run the same `nightly` suite (or, at minimum, the `fixture_server` subset for fast iteration) and compare `STUCK`/`PLANNING` counts, `recovery_success_rate`, and `avg_steps_per_task` against the immediately-prior milestone's report — not against a pre-M0 baseline, so each milestone's individual contribution is isolated.

---

## Part 12 — Success Criteria (measurable, not vague)

1. **Planner no longer repeats an identical `(action_type, target_selector)` pair on two consecutive steps when `recent_actions` shows that pair already attempted with no page change** — verified by: zero occurrences of `sig_action` repeat (the same signature `m0_task_runner.py` already computes for `STUCK` detection) across the fixture regression set, post-M1.3.
2. **`fixture__pagination`, `fixture__login_form`, `fixture__modal_dialog` self-test all reach `COMPLETED`** (not `STUCK`) — the three fixtures used throughout M0.5–M0.9 as the evidence base.
3. **Recent successful actions are present in the transmitted prompt** — verified directly by opening a `--trace` viewer and confirming `provider_request.assembled_prompt` contains a `recent_actions` (or equivalently-named) section listing the prior selector.
4. **Reflection, when triggered, is recorded and inspectable** — a reflected step's trace shows the additional reasoning that led to the changed (or deliberately repeated) action, attributable to the same `step_index`, with `reasoning` explicitly referencing the abandoned prior attempt. (Whether this appears as a second provider request/response pair or as extended content within the existing pair depends on the mechanism chosen in M1.3, Part 10.)
5. **Input values become observable** — a filled-then-re-observed text field's `state.value` in the next step's `observation.elements_summary` matches what was typed; password fields never populate `state.value`.
6. **Zero API breakage** — `AnalyzeRequest`/`AnalyzeResponse`/`PriorStep`/`InteractiveElement`/`PageContext` Pydantic schemas have the exact same field set (names, types, required/optional) before and after M1, confirmed by a schema-diff check.
7. **Existing benchmark regression suite passes unmodified** — the 74 pytest + 22 trace-validation + 35 M0-validation checks (131 total) all still pass after every milestone, with no test file requiring a rewrite (only `test_m0_runner_loop.py`/`test_injection_fidelity.py` gain *new* cases, per Part 11 — no existing assertion is edited to make it pass).
8. **No latency/cost regression on the non-triggered path** — a task whose planner never repeats an action makes exactly the same number of `/analyze` calls before and after M1.3 (proven by the orchestrator unit test in Part 11 asserting single-call behavior when the trigger is false).

---

## Part 13 — Out of Scope (explicitly not in M1)

- Vision / screenshot-based grounding (`app/vision`, set-of-marks) — M3 territory per `docs/architecture-alignment.md`.
- OCR.
- Multi-agent planning or any second independent planner.
- Autonomous browsing without the existing approval/safety gate.
- Cross-session learning (`memory/learning_layer`) — future milestone, not M1.
- Long-term / persistent working memory (`verified_facts` accumulation, `state_engine` population from the benchmark) — explicitly Deferred in Part 3.
- Site-specific intelligence or per-site heuristics of any kind (explicitly forbidden by Part 2 principles).
- Self-healing selectors / ranked locator wiring (`locator_engine.LocatorRanker`) — that is M1-per-the-earlier-roadmap's *original* scope in `docs/architecture-alignment.md`/`benchmark-m0.md`; this specification is narrower and reflects what the M0.5–M0.9 investigations actually proved necessary. Reconciling the two M1 scopes (this reasoning-repair spec vs. the earlier CDP-driver-and-grounding spec) is a sequencing decision for you, not resolved in this document.
- Comet-level autonomy (full closed-loop validate→reflect→recover with the orphaned `execution_gateway` back-half) — this spec's reflection (Part 6) is deliberately a minimal, bounded capability realized within the existing `/analyze` reasoning boundary (mechanism chosen per Part 10, M1.3), not an adoption of the back-half's `recovery`/`exploration` machinery.
- CDP trusted driver, shadow-DOM/iframe traversal — unrelated to the reasoning-loop deficiencies this spec addresses; still a valid, separate future milestone.
- Any change to `execution_gateway`, `mission`, `tabs`, `trust`, `approvals`, or any other orphaned back-half subsystem.

---

## Note on scope reconciliation (flagged, not resolved)

This document specifies **M1 as "fix the reasoning loop"** (the natural continuation of M0.7–M0.9). The earlier `docs/benchmark-m0.md` and `docs/architecture-alignment.md` described **a different M1** ("CDP trusted driver + shadow/iframe + ranked locators"), justified by execution-fidelity evidence gathered *before* RC-1 exposed the planning-layer defects. Both are legitimate, evidence-backed next steps addressing different bottlenecks (execution fidelity vs. reasoning-loop correctness). This specification does not merge, reorder, or choose between them — that sequencing decision belongs to you. If both are wanted, they are independent (no shared files), so either could be M1 and the other M1.5/M2 without rework.
