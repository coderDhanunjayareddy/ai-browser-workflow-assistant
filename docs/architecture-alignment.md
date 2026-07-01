# Architecture Alignment — Designing a Comet-Class Browser Assistant

**Date:** 2026-06-29
**Status:** Design document. No code.
**Sole objective:** Increase real-world browser task completion rate across arbitrary websites. Every recommendation is judged against that one metric.
**Companions:** `docs/architecture-review.md` (audit), `docs/architecture-reconciliation.md` (subsystem reconciliation). This document supersedes their roadmaps with the *shortest* path to the metric.

---

## 0. The Two Facts That Reframe Everything

Before the design, two verified facts that must anchor every decision:

**Fact 1 — The project has no idea how well it performs.** There is **zero measurement of real-world task completion on real websites** anywhere in the repository. Phase F "certification" runs real Chromium but only against **24 synthetic local HTML fixtures** on `127.0.0.1`, with stable `data-testid`s and deterministic state, and asserts **100% pass against that baseline**. That number is meaningless for the stated objective. We are optimizing blind.

**Fact 2 — The capabilities are largely already built, but dead.** Three of the modules that would most move the real-world metric already exist and are real:
- `website_intelligence` — a genuine deterministic semantic-understanding engine (page tree, form/table/dialog/navigation intelligence, prioritized locator builder, execution hints). **Isolated** from the live loop.
- `vision` (`VisionService.verify_visually`) — real Gemini screenshot verification. **Dead** (one unit test, no production caller).
- `locator_engine` (`LocatorRanker`) — real ranked-locator strategy generator. **Dead** (one unit test).

The implication: **the bottleneck is not missing intelligence. It is (a) a weak execution driver, (b) an open loop that never wires perception/validation/recovery together, and (c) the absence of a real benchmark to drive improvement.** This document is therefore mostly about *integration, driver fidelity, and measurement* — not new capability.

---

## Part 1 — The Canonical Architecture of a Comet-Class Browser Assistant

A capable browser agent is not a linear pipeline; it is a **closed perception-action loop with cross-cutting memory and orchestration**. The user's example chain is directionally right but flattens three distinct hard problems (perception vs. understanding vs. grounding) and omits the loop's cross-cutting spine. The corrected canonical model:

> Goal → Plan → **[ Observe → Understand → Ground → Reason → Gate → Execute → Validate → Reflect → Recover ]** ↻ → Complete
> with **Memory** and **Orchestration/Telemetry** cross-cutting the whole loop.

Note on the reference system: "Comet-class" here means Perplexity's Comet pattern — an agent with **first-class, CDP-level control of a real Chromium running the user's actual sessions**, reasoning over both the DOM/accessibility tree and pixels, in a closed loop. The decisive architectural lesson from that class of system is not a specific module; it is **(1) a first-class driver in the real browser, (2) multi-modal perception, (3) a closed loop that reflects and recovers, (4) measured continuously.** Public details of any one vendor are unverifiable, so "how Comet-likely implements it" below is stated as the *architectural pattern that class of system requires*, not as inside knowledge.

For each layer: **responsibility · inputs · outputs · why it exists · do we have it · is ours sufficient · how a Comet-class system implements it.**

### Layer 1 — Goal Intake & Intent
- **Responsibility:** Turn a natural-language request into a typed goal + mode (read/answer/research/act).
- **Inputs:** user message, current page, selection. **Outputs:** structured goal, route.
- **Why:** the rest of the loop needs a stable target and a mode.
- **Have it?** Yes — `intent.router`, `cognitive_core` (entities/goals/references). **Sufficient?** Adequate for the metric; not a bottleneck.
- **Comet-class:** lightweight intent classification + persistent goal/entity memory across turns. Ours matches the pattern.

### Layer 2 — Task Planning / Decomposition
- **Responsibility:** Break a goal into an ordered (re-orderable) set of sub-goals/steps; adapt as the world changes.
- **Inputs:** goal, memory, current understanding. **Outputs:** plan / next sub-goal.
- **Why:** arbitrary tasks are multi-step and the page changes under you; static plans fail.
- **Have it?** Partially. `intelligence.goal_decomposer`/`plan_builder` and `mission/intelligence.next_action_planner` exist but are **heuristic template trees** and **unwired** to the live loop. `execution_planning.planner` is also heuristic. **Sufficient?** No — planning must be LLM-driven and *adaptive* (re-plan on new observations), not template lookup.
- **Comet-class:** the model itself plans and re-plans each turn from fresh observations (ReAct-style), with deterministic structure as scaffolding/guardrails, not as the planner.

### Layer 3 — Browser Observation (Perception)
- **Responsibility:** Capture the current state of the browser: DOM, accessibility tree, **screenshot/pixels**, scroll position, tabs, dialogs, network-idle.
- **Inputs:** live page. **Outputs:** a multi-modal observation snapshot.
- **Why:** you cannot act on what you cannot see; text-only perception is blind to visual/canvas/styled controls.
- **Have it?** Partially. `extractor_v2` captures a11y+DOM+bbox (good) but **no screenshot in the loop**, **no shadow-DOM, no iframe traversal**. `vision` can screenshot-verify but is dead and verification-only. **Sufficient?** No — the single biggest perception gap is no pixels in the loop and no shadow/iframe.
- **Comet-class:** every step captures DOM + a11y + screenshot; set-of-marks overlays number the actionable elements so the model can reason over text and pixels together; pierces shadow DOM and frames.

### Layer 4 — Page Understanding (Semantic)
- **Responsibility:** Turn raw observation into *meaning*: regions (nav/header/footer), forms (fields, required, validation), tables (columns, sort, pagination), dialogs (blocking/dismissible), affordances, loading/wait strategy.
- **Inputs:** observation. **Outputs:** semantic page model + execution hints.
- **Why:** robust action needs structure, not a flat element list; "this is a paginated sortable table with a search box" beats "150 divs."
- **Have it?** **Yes, and it's good** — `website_intelligence` does exactly this (deterministically). But it is **isolated** from the live loop and tuned against synthetic fixtures with clean ids. **Sufficient?** The engine is strong; its *wiring* and *real-site robustness* are the gaps.
- **Comet-class:** a mix of deterministic structural parsing + the LLM's own semantic reading of the screenshot/DOM; the structure is fed into the prompt as grounding.

### Layer 5 — Grounding (Element Targeting)
- **Responsibility:** Map "the intended target" to a **robust, executable locator** (or coordinates) that survives dynamic class names and re-renders; provide fallbacks.
- **Inputs:** semantic model + intended target. **Outputs:** ranked locator candidates / coordinates.
- **Why:** grounding failure is the most common cause of action failure on real sites.
- **Have it?** **Built but dead** — `locator_engine.LocatorRanker` (accessibility_name > aria_label > data > text > grounded_id > css > xpath) and `website_intelligence.locator_builder`. The **live executor ignores all of it** and uses one raw CSS selector. **Sufficient?** No — not because the logic is missing, but because it is not wired and the client can only consume a single selector.
- **Comet-class:** prefers role+accessible-name and text grounding, then visual/coordinate grounding from the screenshot when DOM grounding is ambiguous; always has a fallback ladder.

### Layer 6 — Reasoning / Action Selection
- **Responsibility:** Given goal + understanding + memory, decide the next action(s) with rationale and confidence.
- **Inputs:** compressed multi-modal context. **Outputs:** candidate action(s).
- **Why:** this is the intelligence; everything else feeds or executes it.
- **Have it?** Yes — `ai_service` (Gemini/OpenRouter) is the only real reasoner, and it's reasonably engineered (JSON repair, retry). **Sufficient?** As a single-step text reasoner, yes; but it receives **no pixels and no semantic model**, and is asked for exactly one action with no reflection. The reasoner is under-fed and under-utilized.
- **Comet-class:** multi-modal reasoning over screenshot+a11y+history with an internal scratchpad; proposes an action *and* its expected post-condition (so validation is possible).

### Layer 7 — Risk / Trust / Approval (Safety Gate)
- **Responsibility:** Classify action risk; auto-proceed safe actions; require human approval only for caution/danger.
- **Inputs:** action + context. **Outputs:** allow / require-approval / block.
- **Why:** autonomy without a risk gate is dangerous; approval on *every* step destroys autonomy.
- **Have it?** Yes, twice — a keyword `danger/caution` classifier inside `ai_service.parse_response` (live) **and** a full `trust` engine + `approvals` queue (orphaned). **Sufficient?** The capability exists; the problem is the live path uses the weak keyword version and gates *every* action, not just risky ones.
- **Comet-class:** risk-scoped confirmation (payments, sends, deletes) with everything else autonomous.

### Layer 8 — Execution (Driver)
- **Responsibility:** Actuate the chosen action in the **real browser** with high fidelity (trusted input, focus, scroll, frames).
- **Inputs:** grounded action. **Outputs:** action result.
- **Why:** this is where intent becomes effect; low-fidelity actuation silently fails on modern sites.
- **Have it?** Yes, but weak. Live path: `executor_v2.ts` uses `element.click()` + manual `value` set + dispatched `input`/`change` — **synthetic, untrusted events** that React/Vue controlled components, `isTrusted`-gated handlers, drag/drop, and custom widgets routinely reject; no shadow/iframe. Orphaned path: server-side Playwright on a **separate browser that isn't logged into the user's sites**. **Sufficient?** No — this is the #1 ceiling on real-world completion.
- **Comet-class:** CDP-level **trusted** input (`Input.dispatchMouseEvent/Key`, real focus, native file chooser) inside the user's real, authenticated browser.

### Layer 9 — Validation (Did it work?)
- **Responsibility:** Verify the action achieved its expected post-condition (URL/text/DOM/visual).
- **Inputs:** action + expected post-condition + new observation. **Outputs:** pass/fail + evidence.
- **Why:** without validation the loop is open and errors compound silently.
- **Have it?** Yes, but orphaned — `execution_gateway/browser/execution_validation`, `validators/goal_verifier`, and `vision` (could do visual validation). **Sufficient?** Logic exists; it is **not wired into the live loop**, and visual validation (vision) is dead.
- **Comet-class:** every action declares an expected outcome; validation uses DOM + a screenshot diff/vision check; failure triggers reflection.

### Layer 10 — Reflection
- **Responsibility:** When validation fails (or confidence is low), diagnose *why* and decide what to change.
- **Inputs:** failure + history. **Outputs:** a corrective directive (re-ground, re-plan, wait, scroll, escalate).
- **Why:** the difference between "gives up / asks human" and "figures it out."
- **Have it?** **No, not as an LLM reflection step.** `failure_engine`/`failure_classes` classify errors deterministically; nothing feeds failures back to the reasoner for diagnosis. **Sufficient?** No — this is a core missing behavior.
- **Comet-class:** an explicit reflect step where the model reads the failure + screenshot and proposes a fix before retrying.

### Layer 11 — Recovery / Re-planning
- **Responsibility:** Execute the corrective directive: retry with an alternate locator, wait for network-idle, scroll, dismiss a dialog, re-plan the remaining steps, or escalate to the human.
- **Inputs:** reflection directive. **Outputs:** next loop iteration or escalation.
- **Why:** real sites are non-deterministic; recovery is mandatory for medium/complex tasks.
- **Have it?** Built, orphaned, fragmented — `execution_gateway/browser/recovery`, `recovery/recovery_orchestrator`, `orchestrator/recovery_manager`, `retry_engine`, `rollback_engine`, `exploration`. **Sufficient?** The pieces exist but are duplicated and unwired to the live loop.
- **Comet-class:** bounded recovery ladder driven by reflection, with a budget and a clean escalation to the human.

### Layer 12 — Memory (cross-cutting)
- **Responsibility:** Working memory (verified facts this task), episodic memory (what we did), semantic/site memory (what worked on this domain before).
- **Have it?** Working: yes (`state_engine`, `context_compression`, `cognitive_core`). Episodic: partial (`replay`, timelines). Site/semantic learning: `memory/learning_layer` exists but is thin and unwired. **Sufficient?** Working memory ok; **cross-site learning is the long-term lever** and is barely used.
- **Comet-class:** persistent per-site memory of successful locators/flows so the agent improves with use instead of re-failing.

### Layer 13 — Orchestration, Long-Running Tasks & Multi-Tab (cross-cutting)
- **Responsibility:** Hold the task across many loop iterations, pages, and tabs; coordinate cross-site flows.
- **Have it?** Built, orphaned — `mission`, `unified` task graph, `tabs`, `browser`-sync, `runtime`. **Sufficient?** Capable but unwired; two overlapping task models (`mission` vs `unified`).
- **Comet-class:** a task/session controller that spans tabs and sites with preserved goal + memory.

### Layer 14 — Evaluation / Telemetry (cross-cutting)
- **Responsibility:** Continuously measure real-world task success and per-layer diagnostics.
- **Have it?** **Only against synthetic fixtures** (Phase F). **Sufficient?** No — this is the meta-gap; see Part 7.
- **Comet-class:** a large, versioned real-site eval suite run continuously; every change is judged by it.

---

## Part 2 — Mapping Every Module to the Canonical Architecture

Verdict legend: **Keep** · **Merge** · **Replace** (logic insufficient, rebuild behavior) · **Delete** · **Unknown**. "Current usage" = LIVE (on extension path), ORPHAN (own route/tests only), DEAD (no caller but a test), SHARED (infra).

| Module | Purpose | Canonical layer | Current usage | Problems | Verdict |
|---|---|---|---|---|---|
| extension `extractor_v2.ts` | a11y+DOM+bbox snapshot | 3 Observe | LIVE | no screenshot, no shadow/iframe | **Keep+REFINE** |
| extension `executor_v2.ts` | perform DOM action | 8 Execute | LIVE | synthetic untrusted events, 1 selector, no frames | **Keep+REPLACE driver** |
| extension `service-worker.ts` | message broker / session | 13 Orchestration | LIVE | fine | **Keep** |
| extension side panel (App/hooks) | UI, approval, history | 1/7/14 | LIVE | inline per-step approval | **Keep+REFINE** |
| `intent.router` | classify intent | 1 Intent | LIVE | ok | **Keep** |
| `cognitive_core/*` | entities, goals, refs, conversation, handoff | 1/12 Memory | LIVE | overlaps `conversation` | **Keep+Merge** |
| `conversation/*` | conversation store v2 | 12 Memory | LIVE(assist) | duplicate of cognitive conv mgr | **Merge** |
| `ai_service` | LLM reasoning | 6 Reason | LIVE | text-only input, single action, keyword risk hack | **Keep+REFINE** |
| `services/{summarization,qa,followup}` | assist outputs | 1/6 | LIVE(assist) | ok | **Keep** |
| `services/context_service` | prompt/format/validate | 3/6 | LIVE | ok | **Keep** |
| `context_compression/*` | rank+summarize context | 6 Reason feed | LIVE | element-only; no semantics/pixels | **Keep+REFINE** |
| `extraction_v2/*` (grounded registry, semantics) | ground elements | 4/5 | LIVE | flat; superseded by website_intelligence | **Merge → website_intelligence** |
| `state_engine/*` | verified facts | 12 Memory | LIVE | in-memory; persist | **Keep** |
| `budget_engine/*` | token/step budget | 14/guard | LIVE | ok | **Keep** |
| `replay/*` | timeline, screenshots | 9/12/14 | LIVE | scattered vs other timelines | **Keep+Merge** |
| `orchestrator/workflow_orchestrator` | live loop coordinator | 13 loop control | LIVE | open loop (no validate/reflect/recover) | **Keep+REFINE (close loop)** |
| `orchestrator/recovery_manager` | recovery | 11 Recovery | ORPHAN | duplicate recovery | **Merge** |
| `orchestrator/tab_manager` | tabs | 13 Multi-tab | ORPHAN | overlaps `tabs` | **Merge** |
| `website_intelligence/*` (13 files) | semantic page understanding, forms/tables/dialogs/nav, locator builder, hints | **4 Understand / 5 Ground** | ORPHAN | not wired to live loop; fixture-tuned | **Keep+REWIRE (high value)** |
| `vision/vision_service` | screenshot verification (LLM) | 3 Perceive / 9 Validate | DEAD | verification-only, no caller | **Keep+REWIRE** |
| `vision/vision_policy` | when to call vision | 9/cost | DEAD | unused | **Keep+REWIRE** |
| `locator_engine/*` (ranker, registry, score) | ranked locators | 5 Ground | DEAD | client can't consume; unwired | **Keep+REWIRE (merge w/ resolvers)** |
| `execution_gateway/engine,dispatcher,runner` | execution orchestration loop + retry/rollback | 8/11 loop control | ORPHAN | back-half spine, unwired to live | **Keep (spine)** |
| `execution_gateway/adapter` (contract) | 9-method driver interface | 8 Execute | ORPHAN | **the reuse seam** | **Keep** |
| `execution_gateway/mock_adapter` | test driver | 8 Execute | ORPHAN/test | ok | **Keep (test)** |
| `execution_gateway/browser/playwright_adapter`+`session` | server-side browser driver | 8 Execute | ORPHAN | separate browser, not user session | **Delete-from-prod (test-only)** |
| `execution_gateway/browser/{resolver,adaptive_resolver}` | locator resolution | 5 Ground | ORPHAN | duplicate of locator_engine | **Merge** |
| `execution_gateway/browser/{recovery,failure_classes}` | failure classify + recover | 10/11 | ORPHAN | duplicate recovery | **Merge** |
| `execution_gateway/browser/execution_validation` | post-action validation | 9 Validate | ORPHAN | unwired to live | **Keep+REWIRE** |
| `execution_gateway/browser/{monitor,metrics,exec_timeline,diagnostics}` | telemetry | 14 | ORPHAN | scattered telemetry | **Merge** |
| `execution_planning/*` (planner,validator,rollback) | compile plan steps | 2/8 | ORPHAN | heuristic planner; 2nd ExecutionPlan type | **Keep+Merge plan types** |
| `intelligence/*` (decomposer, plan_builder, opportunity, readiness, advisors) | heuristic planning/advice | 2/6 priors | LIVE(assist research) | heuristic, parallel to LLM | **Merge as priors** |
| `mission/intelligence/*` | heuristic next-action/blocker/readiness | 2/10 priors | ORPHAN | heuristic, unwired | **Merge as priors** |
| `research/*` | multi-source research | 1/6 sub-capability | LIVE(assist research) | ok | **Keep** |
| `decisions/*` (priority, aggregator, feed) | prioritize decisions | 6/7 | ORPHAN | consumes only mission sources | **Keep+REWIRE** |
| `trust/*` (risk, policy, analyzer) | risk classification | 7 Trust | ORPHAN | live path uses keyword hack instead | **Keep+REWIRE (replace hack)** |
| `approvals/*` + `unified/approval_center` | approval queue | 7 Approval | ORPHAN | multiple approval notions | **Merge** |
| `authorization/*` (engine, readiness) | executable contract gate | 7/8 | ORPHAN | unwired to live | **Keep+REWIRE** |
| `governance/*` (contracts, eligibility) | multi-user policy | 7 (future) | ORPHAN | premature for single-user | **Keep (defer)** |
| `mission/*` (lifecycle, store, affinity, memory) | long-running task container | 13 | ORPHAN | overlaps `unified`; in-memory | **Keep+Merge** |
| `unified/*` (task lifecycle, timeline, continuity, task graph) | task tracking on assist | 13 | LIVE(assist) | duplicate task model vs mission | **Merge** |
| `tabs/*` (registry, mappings, snapshot, restoration) | multi-tab state | 3/13 | ORPHAN | overlaps browser/runtime | **Merge** |
| `browser/*` (sync, recommendation, refresh) | browser-event sync | 3/13 | ORPHAN | overlaps tabs/runtime | **Merge** |
| `runtime/*` (context, cache, prefetch, diff, detector) | runtime context (UI metadata) | 3/13 | ORPHAN | "gates nothing"; overlaps tabs/browser | **Merge** |
| `exploration/*` (candidate gen/eval) | alternative generation on failure | 11 Recovery | ORPHAN | unwired | **Keep+REWIRE** |
| `failure_engine/*` (classifier, remedy_db) | error classification | 10 Reflect | ORPHAN | duplicate of failure_classes | **Merge** |
| `recovery/recovery_orchestrator` | recovery | 11 | ORPHAN | duplicate recovery | **Merge** |
| `memory/learning_layer` | cross-site learning | 12 Memory | thin/ORPHAN | barely used | **Keep+REWIRE (long-term)** |
| `validators/*` (site + goal_verifier) | validation | 9 | ORPHAN | per-site validators are brittle | **Keep goal_verifier; Delete per-site** |
| `adapters/{amazon,gmail,mmt,whatsapp}` + `task_graph/*.json` + `site_knowledge/*` | hardcoded per-site scripts | 2/8 | ORPHAN | root cause of "new site→new failure" | **Delete/DEMOTE to hints** |
| `file_engine/file_workflow` | upload/download flows | 8 | ORPHAN | unwired | **Keep+REWIRE** |
| `certification/*` (runner, scenarios, fixtures, reliability, report) | reliability harness over fixtures | 14 Eval | ORPHAN | synthetic fixtures only | **Keep+REPURPOSE → real benchmark** |
| `context/tab_context_engine` | format read view for assist | 3/4 | LIVE(assist) | ok | **Keep** |
| `assist/ambient_assistant` | assist loop | 1/13 | LIVE | ok | **Keep** |
| per-subsystem `registry/persistence/analytics/timeline/inspector` (~77 files) | scaffolding | SHARED | duplicated; persistence stubbed | **Merge → shared infra** |
| `core/{config,database}`, `models/db`, `schemas/*` | infra | SHARED | ok | **Keep** |
| root `scratch/`, `benchmark_v*`, `validate_v*`, `debug_*.json` | dev scratch | — | committed clutter | **Delete from repo root** |

*Nothing is left unmapped.* Every module lands on a canonical layer with a verdict.

---

## Part 3 — The Real Bottlenecks (ranked by impact on real-world completion)

Ranked by how much each *caps* completion on arbitrary real sites. (1) is the hard ceiling; you cannot buy back the others until it is fixed.

1. **Execution driver fidelity (the ceiling).** Synthetic, untrusted DOM events + a single CSS selector + no shadow-DOM/iframe means even correctly-reasoned actions silently fail on React/Vue/SPA sites, custom widgets, framed content, and `isTrusted`-gated handlers. *Why it matters:* every other layer can be perfect and the task still fails at the moment of contact. This alone explains the "works in demo / fails on real site" pattern.
2. **The loop is open (no validate → reflect → recover in the live path).** The live loop suggests one action, a human approves, it executes, and it re-extracts — with **no automatic verification, diagnosis, or recovery.** *Why it matters:* real sites are non-deterministic; without a closed loop, every transient hiccup is a dead end and every step needs a human. This is what makes medium/complex tasks collapse.
3. **No real benchmark (the meta-bottleneck).** You cannot improve, prioritize, or detect regressions on a metric you don't measure. *Why it matters:* it is the reason the project drifted into building 30 subsystems instead of fixing the driver. Arguably this is #1 for the *process*, even though #1 above is #1 for a single task.
4. **Grounding robustness on real sites.** The ranked-locator and semantic-locator logic exists but is dead, and is tuned on fixtures with clean `data-testid`s. Real sites have hashed/rotating classes and no testids. *Why it matters:* grounding failure is the most common *per-action* failure cause after driver fidelity.
5. **No in-loop perception of structure or pixels.** The reasoner gets a flat element list — no semantic page model (`website_intelligence`, built but unwired) and no screenshot (`vision`, dead). *Why it matters:* it blinds the agent to visual controls, layout, and page structure, forcing brittle selector guesses and causing failure on canvas/maps/date pickers/visually-styled UIs.
6. **Adaptive planning for multi-step / long-horizon / multi-tab.** Planning is heuristic templates, unwired; mission/tabs are orphaned. *Why it matters:* cross-page and cross-site tasks (the headline workflows) need a controller that carries goal+memory across many loops and tabs.
7. **Working-memory / state continuity across steps and pages.** Partial today; facts don't reliably carry across navigations and tabs. *Why it matters:* the agent forgets what it already did, repeats steps, or loses the goal.
8. **Prompting & context engineering.** A single 150-line prompt + regex JSON extraction + keyword clarification suppression is doing too much load-bearing work and is fragile across sites and model versions. *Why it matters:* it caps reasoning quality and reliability independent of the model.
9. **Latency & cost.** One LLM call per step, no streaming, no prompt caching. *Why it matters:* not a *completion* blocker, but it caps usable task length and makes long flows slow/expensive — a practical ceiling on complex tasks.

---

## Part 4 — Expected Completion Improvement (engineering estimates)

**Hard caveat:** there is **no measured baseline** (Part 0, Fact 1). The "current" column below is an *engineering estimate* of the live loop's real-world behavior, deliberately more pessimistic than the user's illustrative 95/70/40 because of bottleneck #1 (synthetic events fail on modern SPAs even for "simple" tasks). The first deliverable (M0) replaces this entire column with measured numbers. Treat these as **relative deltas to prioritize work**, not promises.

Task tiers:
- **Simple** — single page, 1–3 actions, mostly standard form controls (clean login, search box, click a clearly-labeled button).
- **Medium** — multi-step on one site, dynamic content, dropdowns/dates/tables (Amazon search→filter→add-to-cart; Gmail compose+send; sortable table edit).
- **Complex** — multi-page/multi-tab/cross-site, auth, infinite scroll, uploads (MMT flight+hotel; YouTube→Gmail→Docs; LinkedIn job search→apply).

| Stage (cumulative) | Simple | Medium | Complex | Rationale |
|---|---|---|---|---|
| **Current (estimated, unmeasured)** | ~65% | ~30% | ~8% | synthetic events fail on SPAs; open loop; brittle 1-selector grounding; human per step |
| **+ M1 Trusted driver (CDP) + shadow/iframe + ranked locators** | ~90% | ~55% | ~20% | actions actually land; grounding fallback ladder; biggest single jump |
| **+ M2 Close the loop (validate→reflect→recover, risk-scoped approval)** | ~95% | ~75% | ~40% | transient failures self-heal; fewer human stalls; medium tasks become viable |
| **+ M3 In-loop perception (website_intelligence + vision/SoM)** | ~97% | ~85% | ~58% | structure + pixels unblock visual/complex UIs, tables, dialogs |
| **+ M4 Multi-step/tab orchestration + memory** | ~98% | ~90% | ~72% | long-horizon & cross-site tasks carry goal/state; cross-site flows complete |
| **+ M5 Site-learning + prompt/context hardening** | ~98% | ~92% | ~78% | improves with use; fewer model-fragility failures |

Reading the table: **M1 and M2 together** (driver + closed loop) deliver the overwhelming majority of the achievable gain and are the cheapest, because they are mostly *wiring existing back-half code to the live loop* plus one new driver. Perception (M3) is the next lever; it is also mostly wiring already-built modules.

---

## Part 5 — The Shortest Roadmap

Five milestones. Each improves task success, is benchmark-measurable, reuses existing work, adds no parallel system, and avoids abstraction-for-its-own-sake. (M0 ships in days; it is the gate for everything after.)

- **M0 — Real benchmark + baseline.** Repurpose the `certification` harness to run the **live loop** against a fixed set of **real sites** (recorded/mirrored where flakiness matters), reporting per-tier completion. Publish the baseline. *Reuse:* certification runner/reliability/report; just swap fixtures→real targets and the adapter→live loop. *No new system.*
- **M1 — Trusted driver + grounding.** Replace synthetic events with **CDP trusted input** via `chrome.debugger` in the extension; add shadow-DOM/iframe traversal to extractor+executor; wire the **ranked locator** logic (`locator_engine` + `website_intelligence.locator_builder`, merged) so the executor tries a fallback ladder, not one selector. *Reuse:* the gateway's 9-method `ExecutionAdapter` contract — add a `UserSessionAdapter` that forwards to the extension; demote server Playwright to test-only.
- **M2 — Close the loop.** Route the chosen action through the existing **gateway** so it runs trust → (risk-scoped) approval → authorization → execute → **validate → reflect → recover** — all reusing the orphaned back-half (`execution_validation`, merged recovery, `exploration`, `trust`, `approvals`). Add one LLM **reflection** step on failure. Reduce human approval to caution/danger only. *Reuse:* nearly everything already built.
- **M3 — In-loop perception.** Feed the reasoner the **semantic page model + execution hints** (`website_intelligence`) and a **screenshot with set-of-marks**; wire **vision** for visual validation gated by the existing `VisionTriggerPolicy`. *Reuse:* website_intelligence + vision (both built).
- **M4 — Long-running tasks + memory.** Merge `mission`+`unified` into one task container; wire `mission`+`tabs` for multi-tab/cross-site flows; persist working state; activate `learning_layer` to remember successful per-site locators/flows. *Reuse:* mission/tabs/unified/learning_layer.

Everything else (governance, horizontal scale, scaffold consolidation) is **deferred** until the metric plateaus — it does not move completion.

---

## Part 6 — Milestone Justification Matrix

| | M0 Benchmark | M1 Driver+Grounding | M2 Close Loop | M3 Perception | M4 Tasks+Memory |
|---|---|---|---|---|---|
| **Why now?** | Can't prioritize blind; gates all else | The hard ceiling; nothing else pays off until actions land | Open loop wastes the new driver; unlocks medium tasks | Reasoner is blind to structure/pixels | Headline workflows are multi-step/tab |
| **Why not later?** | Every later milestone needs it to prove value | Doing M2–M4 on a broken driver shows no gain | Without it, every hiccup needs a human | Grounding still guesses without structure | Premature before single-step is reliable |
| **Risk** | Low (no behavior change); flaky real sites → use mirrors | Med: `chrome.debugger` permission UX; CDP edge cases | Med: reflection loops/cost; bound iterations + budget | Med: vision cost/latency → gate via policy | Med: state/tab complexity; do last |
| **Expected gain** | None directly; enables all gains | Largest single jump (see Part 4) | Second largest; medium tasks viable | Complex tasks viable | Cross-site/long tasks viable |
| **Dependencies** | none | M0 | M0, M1 | M0, M1, M2 | M0–M3 |
| **Revertible?** | Yes (additive) | Yes — feature-flag CDP vs legacy executor | Yes — flag gateway-path vs raw-action path | Yes — flag perception inputs on/off | Yes — per-capability flags |
| **Success measure** | Baseline numbers exist & reproducible | Benchmark simple↑ to ~90%, medium↑ | Medium↑ to ~75%, human-interventions/task↓ | Complex↑ to ~58%, visual-UI category↑ | Complex↑ to ~72%, cross-site category↑ |

Every milestone sits behind a feature flag with the current path as fallback; nothing is promoted until it **beats the previous number on the benchmark.**

---

## Part 7 — The Permanent Evaluation Benchmark

This is the project's most important missing asset. Principles: **real sites; recorded/mirrored where flakiness or auth makes live runs unstable; runs the live loop end-to-end; reports per-tier and per-capability; versioned and run on every change.** The existing `certification` categories already cover most UI patterns — reuse the harness, point it at real targets.

**Global metrics collected on every run (per task):**
- **Task completion** (binary: goal achieved) and **partial progress** (% of required sub-goals reached).
- **Step success rate** (actions that landed and validated / actions attempted).
- **Human interventions required** (count; 0 = fully autonomous).
- **Recovery events** (failures auto-recovered / total failures).
- **Grounding strategy used** (which locator tier succeeded) and **grounding-failure rate**.
- **Wall-clock latency** and **token/$ cost** per task.
- **Failure category** (grounding / driver / understanding / planning / validation / timeout / auth).

**Per-benchmark spec (success / failure / notes):**

| Site / capability | Task | Success criteria | Failure criteria | Notes |
|---|---|---|---|---|
| **Amazon** | search "wireless mouse" → open first result → add to cart | cart count increments; correct item | wrong item; cart unchanged in 3 tries | dynamic listing; popups |
| **Flipkart** | search → apply price filter → read top result price | filter applied; price extracted | filter not applied; no price | hashed classes (grounding stress) |
| **YouTube** | find a specific video → play → read title | video playing; title matches | wrong video; not playing | recommendation noise |
| **LinkedIn** | search jobs by title+location → open first → extract company | results shown; company extracted | login wall not handled; no extract | auth/mirror; rate-limit |
| **Instagram** | open a profile → read follower count | count extracted | login wall; no count | auth-gated; mirror likely |
| **GitHub** | search repo → open → read star count + latest commit | both extracted | wrong repo; missing data | mostly stable DOM |
| **Google Docs** | create doc → type a paragraph → verify text present | text present in doc | canvas not actionable | **canvas/contenteditable — vision stress** |
| **Gmail** | compose → fill recipient/subject/body → (stop at send / send to self) | draft assembled correctly | wrong fields; not assembled | danger gate on send |
| **MakeMyTrip** | search flights (from/to/date) → read cheapest fare | results shown; fare extracted | search not submitted; no fare | heavy SPA; date pickers |
| **Booking** | search hotels (city/dates) → read top price | results; price extracted | search fails; no price | calendars; infinite scroll |
| **Canva** | open a template → change a text element | text changed on canvas | canvas not actionable | **vision/coordinate grounding** |
| **Government site** | locate a specific form/info page → extract a field | target page reached; field read | wrong page; legacy markup breaks grounding | legacy/non-semantic HTML |
| **Banking-like (mock)** | login (test creds) → read balance | balance read | auth flow fails | use a safe mock; never real banking |
| **File upload** | attach a file via `<input type=file>` | native chooser handled; file attached | chooser not handled | needs CDP file-chooser |
| **Download** | trigger a download → confirm file received | file saved | download not captured | |
| **Dialog** | trigger a confirm/modal → handle correctly | dialog dismissed/confirmed as intended | blocked by modal | |
| **Table** | sort a column / edit a row | sort/edit reflected | no change | |
| **Search** | site search → results present | results | empty/error | |
| **Infinite scroll** | scroll until target item loads | item found | gives up early | network-idle waits |
| **Pagination** | navigate to page N → read item | correct page item | wrong page | |
| **Authentication** | complete a login (test account) | post-login state reached | stuck on login | mirror/test creds only |
| **Multi-tab** | open result in new tab → act → return | both tabs coordinated | loses tab context | |
| **Cross-site** | YouTube → copy title → Gmail compose with it | end-to-end goal met | breaks at handoff | the headline integration test |

**Tiering:** each row is labeled simple/medium/complex so Part-4 numbers are reproducible. **Stability:** auth-gated and rate-limited sites run against recorded mirrors in CI and live only in a nightly job, so the benchmark is deterministic enough to gate merges while still sampling reality.

---

## Part 8 — Development Policy (so we never repeat the mistake)

These are hard gates, not aspirations. A change that violates one does not merge.

1. **Benchmark-gated.** No change merges unless it holds or improves the real-site benchmark. "Improves task completion" is the only definition of progress.
2. **No architecture-only milestones.** Refactors/abstractions are allowed only when they directly enable a benchmark-moving change in the same cycle.
3. **No subsystem without a live consumer.** If nothing on the live loop calls it, it does not ship to `main`. (This single rule would have prevented the entire orphaned cluster.)
4. **Everything maps to the canonical loop.** Every module declares which layer it serves and who produces its input / consumes its output. No producer or no consumer → not merged.
5. **Prefer wiring over building.** Before writing a module, prove no existing (possibly orphaned) module already does it. Most of this roadmap is wiring.
6. **One concept, one implementation.** One driver contract, one plan type, one approval, one recovery service, one task container, one telemetry bus. Duplicates are bugs.
7. **Generalize, never patch per-site.** Site-specific behavior may exist ONLY as optional *hints/priors* the general loop may ignore — never as a hardcoded execution path. Fixing one site by adding a script is forbidden; fix the general capability. (This is the direct cure for "new site → new failure.")
8. **The LLM reasons; deterministic code guards.** Heuristics are guardrails, priors, and safety rails around the model — not a parallel "intelligence layer."
9. **Real-session first.** Production execution runs in the user's authenticated browser via the in-extension driver; server-side browsers are for tests only.
10. **Close the loop or don't ship it.** Any new action capability must include its validation and recovery path; open-loop actions are not allowed.
11. **Vertical before horizontal.** Make single-user excellent (completion rate) before persistence/scale/governance.
12. **Docs/ADRs track reality** in the same change that contradicts them.

---

## Final Synthesis

The project's problem was never a shortage of engineering — it was building **parts of one loop in isolation and measuring the wrong thing.** It has already built semantic understanding, ranked grounding, visual verification, a full execution/recovery/trust/approval back-half, and a reliability harness. Almost none of it is wired into a closed loop that runs in the user's real browser, and all of its "results" are measured on synthetic HTML.

The shortest path to a Comet-class real-world completion rate is therefore not new architecture. It is, in order: **(M0) measure real sites; (M1) give the agent a trusted driver and real grounding; (M2) close the loop so it validates, reflects, and recovers without a human at every step; (M3) feed it structure and pixels; (M4) carry tasks across pages and tabs and let it learn.** M1 and M2 — overwhelmingly *wiring existing code* plus one new driver — deliver most of the gain. Everything that does not move the benchmark waits.

Build the benchmark first. Then let the number, not the architecture diagram, decide what gets built next.
