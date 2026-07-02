# Reasoning-Feedback Loop — Architecture

**Status:** Architecture document. Design only — no code, no milestone plan, no estimates.
**Objective:** *When the planner encounters a failed action, every architectural layer should cooperate to avoid repeating that failure.*
**Evidence base (frozen, not re-argued here):** M0.7 (episodic memory loss), M0.8 (generalization + observation incompleteness + the "progress-verdict misfires on fills" caveat), M0.9 (reflection absent), M1.1–M1.3 (memory / observation / reflection implemented), M2 (recovery engine + classifier fix), and the two prompt-level failure-propagation traces on `amazon_in__product_search_price`.

---

## 0. The finding this architecture exists to fix

Across every investigation, one structural fault recurs: **the loop maintains two parallel, incompatible representations of "what the agent already did," and they never converge.**

| | Successful actions | Failed actions |
|---|---|---|
| Channel | `compressed_context.recent_actions` | `compressed_context.important_failures` |
| Shape | structured: `{action_type, selector, value, page_changed}` | unstructured: `{step, error}` — **no selector, no action_type** |
| Read by reflection? | **Yes** (`_detect_repeat_trigger` reads `recent_actions`) | **No** (reflection never reads `important_failures`) |
| Carries recovery diagnosis? | n/a | the diagnosis *string* only, not as a queryable field |

The Amazon trace made the consequence concrete and measurable: the recovery engine correctly diagnosed `OUTSIDE_VIEWPORT`, that diagnosis *reached* `important_failures`, and the planner **still re-selected the identical failed selector** — because (a) the selector was stripped from the failure record, (b) even with the selector present, no prompt rule directs elimination-by-failure-match, and (c) the one deterministic guard that would enforce it (reflection) is wired to the *success* channel. Three independent, necessary conditions, all unmet.

**The architecture's core move is therefore not a new subsystem. It is a data-model unification:** collapse the two memories into one canonical record that every layer reads from and writes to, so a *failed attempt is a first-class citizen with the same addressability as a successful one.* One change to the shape of episodic memory propagates cooperation through the entire loop.

---

## 1. The canonical abstraction — the Attempt Record and the Episodic Attempt Ledger

The spine of the design is a single value type. Success and failure are the **same** type; they differ only in `outcome`.

**Attempt Record** — one per action the agent attempts, within a task:

- **Intent** — `action_type`, `target_selector`, `value`, `description` (the model's own stated purpose for the action).
- **Outcome** — `status ∈ {succeeded, failed, recovered}`; for non-success, a **structured `diagnosis`** drawn from the recovery taxonomy (`OUTSIDE_VIEWPORT`, `OVERLAY_INTERCEPT`, `WRONG_ELEMENT_TYPE`, `DETACHED_STALE`, `AUTOCOMPLETE_LIST`, `NAVIGATION_OCCURRED`, `UNRESOLVED`), never merely a free-text string.
- **Recovery** — `attempted`, `strategy`, `result` (what the recovery engine did and whether it worked).
- **Progress** — `page_changed`, `criteria_advanced`: **neutral observations, not verdicts.** (M0.8's binding lesson: a successful `fill` legitimately changes nothing visible; progress is *information the planner interprets*, never a relabeling of the action's success.)
- **Position** — step index / ordering within the task.

**Episodic Attempt Ledger** — the ordered sequence of Attempt Records for the *current task*. It is the **single source of truth** for "what has already been tried and with what outcome." Today that truth is triplicated and mutually inconsistent (benchmark `prior_steps`, backend `verified_facts`, and compression's split lists); the ledger replaces all three notions of episodic history with one.

Everything below is a contract about how each layer contributes to, or reads from, this ledger.

---

## 2 & 3. Layer contracts — responsibility, ownership, reads, writes (answers Q1–Q3)

For each layer: what it **owns**, what it **reads**, what it **writes**, and — critically for this loop — what it must **not** do.

### Observation
- **Owns:** the complete, faithful snapshot of the page *right now* — elements with full current state (`value`, `checked`, `selected`, `expanded`, per M1.2), URL, visible text, redacted per the security rules (passwords never captured; PII redacted at extraction).
- **Reads:** the live browser only.
- **Writes:** an observation snapshot. Nothing to the ledger.
- **Must not:** carry history. Observation describes *now*, never *what I did*. The M0.7 error was conflating "fresh observation" with "did I already act here" — observation is deliberately blind to the past; remembering is Working Memory's job. Observation's obligation is **completeness** (so the planner can tell an already-filled field from an empty one), not memory.

### Working Memory
- **Owns:** the **Episodic Attempt Ledger** (the canonical record of attempts + outcomes + diagnoses), plus verified facts (extracted data) and the active goal/subgoal.
- **Reads:** Attempt Records produced by the Recovery and Validation layers as each step closes.
- **Writes:** appends the completed Attempt Record; exposes the ledger to Compression.
- **Must not:** hold two shapes for one concept. There is exactly one ledger; a failure is an Attempt Record with `status: failed`, not a different structure in a different field. This is the layer where the two-channel fault is eliminated at the source.

### Compression
- **Owns:** the projection from (full Working Memory + Observation) → planner-sized context, within token budget: element relevance ranking, and **summarization of the ledger into `recent_attempts`** — one list, consistent shape for success and failure alike.
- **Reads:** the ledger + the current observation.
- **Writes:** the compressed context object (internal), now with a single `recent_attempts` channel instead of `recent_actions` + `important_failures`.
- **Must not:** *structurally drop a category of signal.* Compression may **downsample** (keep the last N attempts, drop least-relevant elements) but must never **omit** a whole class — the M0.7 fault (dropping `completed_nodes`) and the M2 fault (stripping selectors from failures) are the same disease: compression deciding some episodic signal doesn't deserve a shape.

### Prompt
- **Owns:** the rendering of compressed context into the model's input, and the **instruction** that tells the model how to use the ledger.
- **Reads:** the compressed context.
- **Writes:** the assembled prompt (backend-internal).
- **Must not:** present attempts without the rule for using them. Two obligations the current prompt fails: (a) render `recent_attempts` as *attempts-with-outcomes*, not just "recent executed steps"; (b) carry an explicit elimination rule — *do not propose an action whose `(action_type, target_selector)` matches a prior attempt marked `failed`, unless the page state has materially changed.* The prompt-level trace proved that even with perfect data, no such rule exists today, so a rule-following model may legitimately repeat the failure. Cooperation must be **stated**, not hoped for.

### Planner
- **Owns:** the single semantic reasoning step — choosing the next action from goal + observation + ledger.
- **Reads:** the compressed context (with `recent_attempts`) and prompt rules.
- **Writes:** a candidate action (`SuggestedAction`).
- **Must not:** be the *only* guard against repetition, and must not re-derive history. The planner is fallible and non-deterministic; the architecture gives it the information and the instruction, but places a deterministic backstop (Reflection) after it precisely because "hope the LLM infers it" is what M0.9 proved insufficient.

### Reflection
- **Owns:** the deterministic post-planner check — does the candidate action repeat a *known-failed* attempt with no intervening state change? — and the bounded corrective directive when it does.
- **Reads:** the **unified ledger** (`recent_attempts`). This is the pivotal correction: reflection must read attempts *of both outcomes*, so that a repeat of a **failed** action triggers it. Today `_detect_repeat_trigger` reads only the success channel, so the exact Amazon repeat is invisible to it. Under the unified ledger this ambiguity cannot recur — reflection reads "attempts," and a failed attempt is an attempt.
- **Writes:** either passes the candidate through, or forces a re-plan / veto carrying the specific abandoned `(selector, diagnosis)`.
- **Must not:** silently repeat, and must not be an unbounded self-argument. It is the layer that converts "the data says this already failed" into an *enforced* consequence.

### Execution
- **Owns:** high-fidelity actuation of the chosen action (trusted input via the driver).
- **Reads:** the (possibly reflection-revised) action.
- **Writes:** an `ExecResult` — success/failure + which locator strategy resolved.
- **Must not:** decide what to do on failure. Its output is a fact ("it failed, here's the raw signal"), not a remedy.

### Recovery
- **Owns:** on execution failure, DOM-level **diagnosis** and a bounded, generic recovery attempt; and — the part this loop most depends on — emitting a **structured** outcome, not an error string.
- **Reads:** the failed action + the live page.
- **Writes:** the `outcome`, `diagnosis`, and `recovery` fields of the Attempt Record. Recovery is where a failure acquires *meaning* (a typed diagnosis, tied to the selector that failed). That structured meaning is exactly the information the M2 trace showed being flattened into a stringy `important_failures.error` with the selector lost.
- **Must not:** manufacture false success, and must not let a diagnosis escape as prose. If it cannot recover, it must hand Working Memory a *queryable* failure, not a sentence.

### Validation
- **Owns:** determining whether the action achieved its intended effect / advanced the goal criteria (post-action DOM/URL/criteria comparison).
- **Reads:** the before/after observations + success criteria.
- **Writes:** the `progress` fields of the Attempt Record (`page_changed`, `criteria_advanced`) — **as neutral data**.
- **Must not:** convert progress into a verdict that overrides execution status. M0.8 proved that "no page change ⇒ failure" misfires on fills; validation reports *what changed*, the planner and reflection *interpret* it. Validation informs memory; it does not relabel history.

### Back to Memory
- The now-complete Attempt Record (intent + outcome + diagnosis + recovery + progress) is appended to the ledger. This closes the loop: **every layer contributed a field to one coherent record, and the record returns to the single memory the next cycle reads.** "Cooperation" is precisely this — not new coordination machinery, but one shared record that each layer fills in its own field of.

---

## 4. What must never be duplicated (answer Q4)

- **Episodic history has exactly one home: the ledger in Working Memory.** The current triplication — benchmark `prior_steps`, backend `verified_facts`, and compression's `recent_actions`/`important_failures` — collapses to one source that Compression *projects* (never re-derives) and everyone else *reads*.
- **A given fact about an attempt (its selector, its outcome, its diagnosis) exists once.** Success and failure do not get separate, differently-shaped copies of "an action happened."
- **Observation must not duplicate memory.** The current page (Observation) and the record of past attempts (Memory) are distinct concerns; an element appearing in `relevant_elements` is not a statement about whether it was already tried — that statement lives only in the ledger.

## 5. What is transient (answer Q5)

- The **per-task Episodic Attempt Ledger** — cleared at task boundary; it is memory *of this task*, not of the agent.
- The **current observation snapshot** — replaced every step.
- The **reflection directive** — exists only for the one corrective re-plan.
- Per-task verified facts — transient to the task unless explicitly promoted (below).

## 6. What should become long-term memory (answer Q6)

- **Cross-task / cross-site learned priors** — e.g. "on this domain, this control is a decoy; this strategy resolves this diagnosis" — abstracted from many tasks' ledgers. This is the *only* information that outlives a task, and it is **explicitly outside this loop's core**: the loop is the per-task feedback substrate; long-term memory is a consumer of it. The design's payoff is that the *same Attempt Record shape* is what a future long-term memory would aggregate — the loop is built so that learning-from-failure-over-time becomes a natural extension, not a rewrite.

## 7. What is benchmark-only (answer Q7)

- The benchmark's `M0StepRecord` / `M0TaskResult`, reliability metrics, report JSON/MD/HTML, trace files, screenshots, DOM snapshots on disk, the fixture server, and the two-executor (playwright/synthetic) plumbing.
- These are a **measurement mirror** of the same Attempt Records, persisted for evaluation. They must never enter the reasoning loop or influence a planning decision — the benchmark *observes* the loop, it is not a layer of it. (The credit-exhaustion contamination in the M2 run is a reminder of why this boundary matters: benchmark-side accounting is separate from the agent's own state.)

## 8. What must never leave the backend (answer Q8)

- Provider keys (already enforced), the raw provider-facing prompt assembly, the SYSTEM_PROMPT text/version, and the full uncompressed page context beyond what is transmitted.
- **Sensitive observed values** — passwords are never captured at all; PII is redacted at Observation, *before* it can enter Memory or the ledger. Redaction is an Observation-layer obligation so no sensitive value ever becomes episodic memory.
- The internal structure of the compressed context and the ledger — these live inside the opaque planner input, not on any client-visible wire field.

---

## 9. Interfaces that change (answer Q9) — all internal

- **`StateSummarizer` output:** one `attempts` collection (success and failure as one shape), replacing the `completed_nodes` / `important_failures` split.
- **`compressed_context` internal shape:** `recent_attempts` (unified) supersedes `recent_actions` + `important_failures`.
- **Reflection's data source:** `_detect_repeat_trigger` reads the unified ledger, so failed-action repeats are in scope.
- **The episodic record entering the backend** (the `PriorStep` notion): failures carry `target_selector`, `action_type`, `value`, and structured `diagnosis`, symmetric with successes — via existing free-form/additive-optional fields, not a wire-schema break.
- **`ExecResult` → Attempt Record write-back:** recovery's structured diagnosis becomes queryable fields, not a message string.
- **The Prompt rendering + one SYSTEM_PROMPT rule:** render attempts-with-outcomes and instruct elimination-by-failure-match.

These are contracts *between layers inside the backend and the benchmark caller* — the shape of episodic memory as it flows, not the public surface.

## 10. APIs that remain unchanged (answer Q10)

- **`AnalyzeRequest` / `AnalyzeResponse` Pydantic schemas at the wire level** — the unification lives inside the opaque compressed-context string and inside the existing `PriorStep` free-form/optional fields; no field is removed or retyped at the boundary.
- **The extension ↔ backend `/analyze` contract**, the **benchmark ↔ `/analyze` contract**, and the **trace schema** (`planner_trace_v1`, additive-only by its own rule) all hold. A caller that has not adopted the richer episodic record still functions; it simply provides a less complete ledger.

---

## 11. Alignment with the general-purpose browser agent (answer Q11)

A general-purpose agent — the Comet-class target from the alignment doc — is defined less by any single capability than by one property: **it does not repeat its own mistakes, within a task and eventually across tasks.** That property is impossible while "what I did" and "what failed" live in two incompatible memories that the reasoning layers read inconsistently.

This architecture makes failure a **first-class, structured, addressable, single-sourced** part of the agent's episodic state, and makes *every* layer a contributor to one shared record rather than an owner of a private, partial view. That yields three vision-level properties:

1. **Generality by construction** — because the fix is the *shape of memory*, not a per-site or per-failure patch, one change improves every multi-step workflow on every site (M0.8's requirement that a single improvement lift many websites).
2. **Determinism where it matters** — reflection enforces non-repetition as a guarantee rather than an LLM hope (M0.9's requirement), because it now reads a memory that includes failures.
3. **A substrate for learning** — the same Attempt Record that closes the per-task loop is the unit a future long-term memory aggregates into site/strategy priors, so the agent that "improves with use instead of re-failing" becomes an extension of this loop, not a separate build.

---

## Architectural thesis (one sentence)

*Unify success and failure into a single canonical Attempt Record that flows through one episodic ledger every layer reads from and writes to — so that when the planner encounters a failed action, the failure is remembered with the same fidelity, addressability, and reflective enforcement as a success, and no layer is left holding a private, partial, or incompatible view of what already happened.*
