# Planner Contract V2 — Architecture

**Status:** Architecture document. Design only — no code, no implementation plan, no milestones, no estimates.
**Scope:** the planner's output contract and how the orchestrator routes it. Grounding (Observation → Representation → Ranking → Compression) is unchanged and out of scope.
**Evidence base (frozen, not re-argued here):** the planner-contract investigation established that `SuggestedAction.action_type` is a closed, action-only enum; `SYSTEM_PROMPT` frames every turn as "suggest the NEXT browser action" and "ONE action at a time"; the one real completion-without-action path (`action is None` → recheck criteria) exists in the orchestrator loop but is never described to the model; and an extraction-shaped clarification attempt is detected and overridden with a forced `scroll` action. The Amazon accordion-click loop is the direct, measured consequence: the price was present in the observation, but the contract offered no way to say so.

---

## 0. The finding this architecture exists to fix

The planner is not under-informed and not reasoning poorly given its freedom — it has no freedom. Its entire output space, by contract, is "which browser action." When the correct turn is not an action — the answer is already visible, the page is mid-transition, the user must decide something, or the current approach needs to change — the contract has no shape for that turn, so the model is forced to manufacture an action-shaped answer to a non-action question. That forcing is the mechanism behind the observed failure, and it is generic: any task where the right next turn is to *report*, *wait*, *ask*, or *change approach* hits the same wall, not only Amazon's price accordion.

**The architecture's core move is therefore not a new subsystem. It is a contract widening:** replace "the planner always returns an action" with "the planner returns one typed outcome, of which action is one kind among several," and let the orchestrator — which already loops, already tracks state, already decides when a task is done — dispatch on the kind. One change to the shape of the planner's output propagates the missing degrees of freedom through the whole loop.

---

## 1. The planner's responsibility (answers Q1)

Unchanged in essence, widened in output: **given the current goal, the current observation, and the episodic ledger, decide the single most appropriate next outcome — and produce it.** "Most appropriate" today means "which action"; under V2 it means "which *kind* of turn is this, and what is its content." The planner still makes exactly one decision per turn (the existing "one action at a time" discipline is preserved as "one outcome at a time"), still reads only what Compression hands it, and still performs no side effect itself — it *proposes*, others *act on the proposal*. Nothing about the planner's position in the pipeline moves; only the shape of what leaves it changes.

## 2. The orchestrator's responsibility (answers Q2)

The orchestrator is the existing task loop (the same loop already coded as the benchmark's task runner and, conceptually, whatever drives the extension's live session) — its role does not change in *kind*, only in what it now dispatches on. It:
- invokes Observation → Representation → Ranking → Compression → Planner, unchanged;
- **routes the planner's outcome by kind** to the correct downstream handler (below);
- owns step/time/token budgets and loop termination, unchanged;
- owns the authoritative check of whether the task's success criteria are actually satisfied — the planner may *claim* an outcome, the orchestrator *verifies* it against real criteria before ending the loop, exactly as it already re-checks criteria today after every step.

The seed of this already exists: today's `action is None → recheck criteria → complete` branch is a single, ad hoc special case of exactly this dispatch. V2 generalizes an already-present mechanism; it does not invent one.

## 3. Which decisions belong to the planner, and which belong elsewhere (answers Q3)

| Decision | Owner | Changed? |
|---|---|---|
| What kind of turn this is, and its semantic content (which action, what answer, why wait, what question, why replan) | **Planner** | Widened, not new |
| Is a proposed action safe, or does it need human approval | Gate / safety classification | Unchanged |
| How to actuate a chosen action; diagnose an execution failure | Execution / Recovery | Unchanged |
| Did an action produce real progress | Validation | Unchanged |
| Does a *repeated* action match a known-failed attempt | Reflection | Unchanged |
| Is a *claimed* completion/answer actually correct | **Validation** (extended) | Same mechanism, one more thing to check |
| Is the task as a whole done; when does the loop end | Orchestrator | Unchanged |
| Cross-task learning | outside this contract | Unchanged |

The planner decides *what this turn is*; every layer that currently guards, verifies, or reacts to a turn keeps doing exactly that job, on a slightly richer set of turn shapes.

## 4. What the planner may return besides actions (answers Q4)

One outcome, tagged with exactly one kind:

- **Act** — today's `SuggestedAction`, unchanged shape (action_type, selector, value, description, reasoning, safety).
- **Report** — the goal (or the active sub-goal) is already satisfiable from what is currently known: carries an optional extracted value and an assertion that criteria are met. Covers both "here is the answer" and "nothing further is needed" — the same shape, since both are "no action, a claim about the goal."
- **Wait** — the page is mid-transition and needs time before the next observation is meaningful. (This already exists today, disguised as an `action_type`; V2 only re-homes it as its own kind so it is never mistaken for an interaction.)
- **Ask** — a question only the user can answer. Unifies today's bolted-on `clarification_question` into a first-class, equally-weighted outcome instead of an optional side-field the backend half-suppresses.
- **Replan** — the planner's own recognition, from this turn's reasoning, that the current approach or active sub-goal will not work and a different strategy is needed.

**Deliberately not a planner outcome: Recovery.** Recovery is reactive and execution-triggered — it only ever engages after an **Act** outcome's execution fails. The planner does not request recovery; recovery is entered, not asked for. Naming it as a planner outcome would duplicate a responsibility Recovery already owns cleanly.

## 5. How each outcome is represented (answers Q5)

- **Act** — unchanged from today.
- **Report** — a claim, not a verdict, mirroring the reasoning-feedback-loop architecture's own principle that *validation reports neutral observations, the loop interprets them.* A Report is the planner's neutral claim; the orchestrator independently checks it against real success criteria before trusting it — the planner is never self-certifying.
- **Wait** — a duration/condition, carrying no selector and no execution semantics, so Validation/Recovery never mistake an elapsed wait for a failed interaction (a real ambiguity in today's scheme, where `wait` is technically an "action").
- **Ask** — a question plus (implicitly) a pause in the loop until the user answers. The existing "is this actually something only the user can supply" filter (currently a string-matching patch on the parsed response) becomes the orchestrator's explicit job of validating an **Ask** outcome before surfacing it — same check, promoted from a parsing-time patch to a contract-level responsibility.
- **Replan** — a stated reason plus (optionally) a revised framing of the sub-goal, fed back into the very next planning turn's context. Distinct from Reflection's veto: Reflection intercepts a proposed **Act** *after the fact*, from ledger history; Replan is the planner's *own* real-time judgment, before any action is even proposed. The two do not overlap because they trigger at different points in the sequence — one reactive-and-deterministic, one proactive-and-semantic — and neither substitutes for the other.

## 6. How outcomes flow through the existing architecture without a parallel system (answers Q6)

Every outcome — whatever its kind — becomes **one Attempt Record in the same Episodic Attempt Ledger** the reasoning-feedback-loop architecture already defines, just with kind-appropriate fields instead of forcing every turn into an action-shaped record. There is one loop, one memory, one dispatch point:

- **Act** → Reflection (checks ledger for a matching prior failure) → Execution → Recovery-on-failure → Validation → ledger append. *Exactly today's path.*
- **Report** → Validation (checks the claim against real success criteria, the same before/after-comparison machinery, applied to a claim instead of a DOM diff) → ledger append → orchestrator finalizes if verified.
- **Wait** → orchestrator holds, re-observes → ledger append (a neutral "waited" record, not a success/failure of an action).
- **Ask** → orchestrator surfaces the question, pauses the loop → ledger append once answered.
- **Replan** → orchestrator immediately re-invokes Compression/Planner with the stated reason folded into context → ledger append (a record of *why* the approach changed, available to future reasoning exactly as a failed attempt is today).

No second loop, no parallel state store, no new pipeline stage. One outcome-typed turn enters the one loop that already exists.

## 7. What remains unchanged (answers Q7)

- **Observation, Representation, Ranking, Compression** — untouched; this document does not concern grounding.
- **Execution** — unchanged; still only actuates a chosen **Act**.
- **Recovery** — unchanged; still reactive, still only **Act**-triggered.
- **Reflection** — unchanged in contract; still reads the unified ledger, still intercepts a proposed **Act** using exactly the mechanism the reasoning-feedback-loop architecture already specifies.
- **Validation** — unchanged mechanism; gains one more comparison target (a **Report** claim), using the same "neutral observation, not a verdict the planner can self-issue" principle it already applies to actions.
- **Working Memory / State Engine / Timeline (the Episodic Ledger)** — unchanged in role and shape philosophy; the Attempt Record remains the one canonical unit, its `intent` field simply admits five kinds instead of assuming Act.
- **Workflow Orchestrator** — unchanged in *kind* of responsibility (sequencing, budgets, termination); see §8 for what grows.

## 8. What conceptually changes (answers Q8)

Exactly two things, both already implied above:

- **The planner's output contract** — from "a list of actions plus a bolted-on optional clarification field" to "one typed outcome, of exactly one of five kinds." This is the entire change.
- **The orchestrator's dispatch** — from "always hand the action to Execution" to "route by outcome kind" (§6). The orchestrator already contains the seed of this (`action is None` → recheck); V2 makes the dispatch exhaustive instead of a single special case.

Everything the loop talks to *outside* the planner — the wire contracts already frozen by the reasoning-feedback-loop and observation-grounding architectures, the benchmark/executor contracts, the ranking/compression contracts — is unaffected. This is a change to one contract (the planner's output) and one routing table (the orchestrator's dispatch), not a new architecture layer.

## 9. Why this is a step toward a human-like assistant, not an action-bot (answers Q9)

A person handed this same task, seeing the price already printed on the page in front of them, simply *says the number*. They do not click on the price to "activate" it. Today's contract cannot produce that turn at all — its entire vocabulary is "I will now interact with something." Planner Contract V2 makes "just tell you" a real, structurally legitimate turn, on equal footing with acting, for the first time.

The same generalization covers the rest of the outcome set: a human assistant also sometimes waits for a page to settle, sometimes asks a clarifying question instead of guessing, and sometimes says "that approach isn't working, let me try something else" — none of these are "browser actions," and today's contract either has no shape for them (replan, report) or actively suppresses the attempt (the extraction-clarification override that force-injects a scroll). Widening the contract to admit these as first-class, undiscouraged outcomes is precisely the missing degree of freedom between a bot that always pushes a button and an assistant that acts only when acting is actually the right thing to do.

## 10. End-to-end workflow — before and after

### Before Planner Contract V2

```
Observation → Representation → Ranking → Compression
                                                │
                                                ▼
                                            Planner
                                  (contract: ONE action, always —
                                   clarification_question is an
                                   optional side-field, often
                                   suppressed/overridden)
                                                │
                                                ▼
                                            Reflection
                                    (checks ledger for repeat)
                                                │
                                                ▼
                                            Execution
                                          success? ── failure?
                                             │             │
                                        Validation      Recovery
                                     (dom_changed /   (diagnose, one
                                      criteria check)   bounded retry)
                                             │             │
                                             └──────┬──────┘
                                                    ▼
                                     Working Memory / Ledger
                              (only an action's success/failure
                               is representable — no shape for
                               "the answer was already visible")
                                                    │
                                                    ▼
                                          Orchestrator loop
                                (continues issuing actions; if the
                                 right turn was never an action,
                                 criteria never pass by side effect
                                 → STUCK / repeated-loop failure)
```
*This is the exact shape of the Amazon failure: the price was in the observation, but no turn existed that could simply say so — so the loop clicked the price label, twice, until STUCK.*

### After Planner Contract V2

```
Observation → Representation → Ranking → Compression
                                                │
                                                ▼
                                            Planner
                             (contract: ONE outcome, of one kind)
                                                │
              ┌────────────┬────────────┬──────┴──────┬────────────┐
              ▼            ▼            ▼             ▼            ▼
             Act         Report        Wait          Ask        Replan
              │            │            │             │            │
              ▼            ▼            ▼             ▼            ▼
         Reflection    Validation    Orchestrator  Orchestrator  Orchestrator
         (checks       (checks       holds, then   surfaces to   re-invokes
          ledger for    claim vs      re-observes   user, pauses  planner next
          repeat)       real                        the loop      turn with
              │         criteria)                                 reason in
              ▼            │                                      context
         Execution         │
        success?fail?      │
           │      │        │
      Validation Recovery  │
           │      │        │
           └──┬───┘        │
              ▼            ▼
      Working Memory / Episodic Ledger
      (every kind of outcome becomes one
       Attempt Record — Act, Report, Wait,
       Ask, and Replan all addressable,
       all readable by future reasoning)
                    │
                    ▼
             Orchestrator loop
   (routes the next turn from the ledger + real
    criteria; terminates on orchestrator-verified
    completion — a Report claim, verified — not only
    on an action's incidental side effect)
```
*Same pipeline, same layers, same ledger. The only structural addition is that the planner's single decision each turn is now "which of five kinds," and the orchestrator already knows how to route all five into the loop it already runs.*

---

## Architectural thesis (one sentence)

*Widen the planner's contract from "always produce a browser action" to "produce one typed outcome — act, report, wait, ask, or replan" — and let the orchestrator, which already loops, already tracks the episodic ledger, and already contains the seed of this dispatch in its no-action completion check, route each outcome to the one layer that already owns its consequence, so that a turn whose right answer is "the value is already here" or "I should ask" or "this approach isn't working" is no longer forced into the shape of a click.*
