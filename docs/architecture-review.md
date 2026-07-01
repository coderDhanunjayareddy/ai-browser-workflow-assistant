# Architecture Review — AI Browser Assist

**Date:** 2026-06-29
**Scope:** Whole-system architecture, execution model, comparison with state-of-the-art browser agents, scalability/maintenance trajectory, and strategic recommendations.
**Method:** Read of the live request path (extension → `/analyze` / `/assist` → AI service → content-script executor), the v2.0→v9.0 + Phase B–F backend, and corroborating sweeps of wiring, "intelligence" internals, and the test/benchmark suite.

---

## 1. Executive Summary

The repository contains **two architecturally disjoint systems wearing one name**:

1. **The live product** — a small, coherent, human-in-the-loop browser copilot. The Chrome extension extracts an accessibility-flavored DOM snapshot, the backend compresses it and asks Gemini/OpenRouter for **one** next action, the user approves, and a content script performs a CSS-selector `.click()`/`.value` set. This path is ~8 modules and is the only place real AI runs.

2. **The "platform" backend (V3.0 → Phase F)** — ~30 subsystems, ~250 modules, ~180 test files implementing missions, trust, governance, authorization, runtime, decisions, approvals, execution-planning, an execution-gateway, and a server-side Playwright executor. **18 of the route modules are registered but never called by the extension.** Every "intelligent" module in this stack is **100% deterministic heuristics — zero LLM calls.** State lives in in-memory TTL dicts; the `persistence.py` modules are stubs; Playwright isn't even in `requirements.txt`.

**The central finding:** the project has invested the overwhelming majority of its engineering effort into a parallel, unintegrated, AI-free scaffolding layer, while the actual product value remains a thin single-step Gemini loop whose execution and perception primitives are materially weaker than current state-of-the-art browser agents. The versioned milestone process (V2.3, V2.5, … V9.0, Phase B–F) has been **manufacturing breadth, not depth** — each milestone adds a new parallel subsystem with its own models/registry/persistence/analytics/timeline/inspector scaffold rather than deepening the one loop that ships.

This is recoverable, and much of the underlying code is clean and well-tested *in isolation*. But the strategic trajectory is unsustainable: the gap between the stated goal (autonomous multi-step automation of 10 hard cross-site workflows) and the measured reality (sub-millisecond heuristic latency + structural file-presence checks) is widening with every milestone.

---

## 2. The System As It Actually Runs

### 2.1 Live request paths (the only code the extension exercises)

The extension makes exactly these backend calls:

| Endpoint | Purpose |
|---|---|
| `POST /analyze` | Suggest the next browser action |
| `POST /assist` | Chat / summarize / ask / research front door |
| `POST /workflow/log`, `GET /workflow/history`, `GET /workflow/{id}/analytics` | Event logging, history, analytics |

`POST /analyze` → `WorkflowOrchestrator.orchestrate_analysis()`:

```
extractor_v2 (a11y snapshot, ≤150 elements)
  → GroundedElementRegistry          (extraction_v2)
  → StatePersistence facts           (state_engine)
  → ContextCompressor → ≤30 elements (context_compression)
  → [cognitive_context if handoff]   (cognitive_core)
  → BudgetManager.enforce            (budget_engine)
  → ai_service.analyze → Gemini/OpenRouter → ONE SuggestedAction
  → TimelineService.record           (replay)
→ user approves in side panel
→ executor_v2.executeActionV2 (content script) performs the DOM action
→ re-extract, repeat
```

`POST /assist` additionally reaches `intent.router`, `assist.ambient_assistant`, the `services/{summarization,qa,followup}`, `conversation`, `cognitive_core`, and `unified.task_lifecycle/timeline`.

**Wired, real subsystems (~10):** `extraction_v2`, `context_compression`, `state_engine`, `budget_engine`, `replay`, `cognitive_core`, `intent`, `assist`, `conversation`, `unified` (partial), `services/ai_service`.

### 2.2 The orphaned stack (registered in `main.py`, never called by the product)

`mission`, `mission_intelligence`, `tabs`, `trust`, `browser` (sync), `decisions`, `approvals`, `governance`, `authorization`, `runtime`, `plans` (execution_planning), `gateway` (execution_gateway + Playwright), `website_intelligence`, `certification`, `intelligence`, `research`. These are reachable only through their own HTTP routes and their own test/benchmark scripts.

### 2.3 The "intelligence" is not intelligent

Every decision module in the orphaned stack is hardcoded heuristics — keyword frozensets, lookup tables, weighted scoring formulas, boolean rule chains. Representative (all verified, no AI imports):

- `execution_planning/planner.py` — keyword→action templating
- `intelligence/goal_decomposer.py` — hardcoded template trees per `ActionType`
- `mission/intelligence/*` — documented "always deterministic, no LLM, <0.5ms"
- `trust/risk_classifier.py`, `policy_engine.py` — action→risk lookup + substring fallback
- `governance/eligibility.py` — five booleans ANDed
- `decisions/priority.py` — "No LLM. No ML. Pure rule-based scoring."
- `failure_engine/classifier.py` — substring matching on error text

These are fine as fast deterministic guards. They are **not** the "AI-driven workflow reasoning" the product is positioned around, and labeling them as an intelligence layer hides that the only semantic reasoning in the system is the single Gemini call.

---

## 3. The Execution Model — Three Disjoint Designs

The repo contains three independent ways to "execute a browser action," none unified, only one live:

| Model | Where | How it acts | Session/cookies | Status |
|---|---|---|---|---|
| **Content-script executor** | `extension/content/executor_v2.ts` | `document.querySelector` + synthetic `.click()`/`.value` + `input`/`change` events | Uses the **user's real logged-in Chrome** | **LIVE** |
| **Static task-graph adapters** | `task_graph/*.json` + `adapters/{amazon,gmail,mmt,whatsapp}` | Pre-scripted per-site node graphs | Real Chrome (via extension) | Partially wired; site-specific, brittle |
| **Server-side Playwright gateway** | `execution_gateway/browser/*` | Playwright on a backend-spawned Chromium, deterministic locator resolution | **Separate browser — NOT the user's session** | Orphaned; Playwright not installed |

Critical observations:

- **The Playwright gateway reintroduces the exact complexity ADR-006 deferred** ("server-side browser instance with session/cookie synchronization — significant complexity with no MVP benefit") — but does so *in parallel* with, not as a replacement for, the content-script path, and without solving cookie/session sync. A backend Chromium is not logged into the user's Gmail/Amazon, so it cannot complete the very workflows the project targets.
- **The live executor uses synthetic, untrusted DOM events.** `element.click()` and manual `value` assignment + dispatched `input`/`change` are routinely ignored or mishandled by React/Vue controlled inputs, frameworks that gate on `isTrusted`, drag/drop, file pickers, custom dropdowns, canvas, and `<iframe>`/shadow-DOM boundaries. The extractor does not pierce shadow DOM or traverse cross-origin frames.
- **Selector strategy is brittle.** `buildSelector` falls back to `tag[role] > tag:nth-of-type(n)` chains capped at depth 5 — these break on the dynamic, hashed-class, deeply-nested SPAs (Flipkart, MakeMyTrip, LinkedIn) the product explicitly targets.
- **The loop is single-action, full-round-trip.** Every step = re-extract DOM → compress → full LLM call → human approval → execute. Latency and token cost scale linearly with steps; a 20-step booking flow is 20 Gemini calls and 20 approvals.

---

## 4. Comparison With State-of-the-Art Browser Agents

Reference points: Anthropic Computer Use, OpenAI Operator/CUA, `browser-use`, Skyvern, WebVoyager-class research agents, and CDP/Playwright-driven agents.

| Dimension | This system (live path) | SOTA browser agents |
|---|---|---|
| **Perception** | a11y-text snapshot (roles, names, bbox); images only on a special "extraction task" branch | Screenshot + set-of-marks vision **and** a11y tree; pixel grounding for canvas/visual layout |
| **Grounding/acting** | CSS selectors + synthetic events from content script | CDP/Playwright trusted input, or pixel/coordinate clicks; pierces shadow DOM, handles iframes, file chooser, downloads |
| **Control loop** | One action per LLM call, human approval each step, re-extract each step | Autonomous observe→reason→act loops with internal multi-step planning; ask-human only on ambiguity/risk |
| **Planning** | Implicit, single-step ("suggest the next action") | Explicit task decomposition + replanning on failure, often with a scratchpad/memory |
| **Self-healing** | None in the live path (orphaned `adaptive_resolver`/`recovery` are deterministic and unused by the extension) | Retry with alternate locators, vision fallback, reflection on failed steps |
| **Session model** | ✅ **Real user session** (genuine advantage) | Often a fresh/managed browser needing auth bootstrapping |
| **Safety** | ✅ **Explicit per-action approval + server-side allowlist + danger/caution classifier** (genuine advantage) | Usually coarser; approval often only on high-risk actions |
| **State/memory** | Verified-facts store + budget + timeline (reasonable) | Episodic memory, DOM diffing, trajectory replay |

**Where this system is genuinely ahead:** safety posture (hard approval gate, server-side allowlist, PII redaction in the snapshot, API keys server-only) and the decision to operate inside the user's authenticated browser. These are real, defensible product differentiators.

**Where it lags materially:** perception (no vision in the loop), grounding robustness (synthetic events, brittle selectors, no shadow/iframe handling), autonomy (single-step, approval-per-action), and failure recovery (the recovery machinery exists but is bolted to the orphaned Playwright path, not the live one). On the 10 target workflows, these gaps — not the absence of a governance subsystem — are what will determine success or failure.

---

## 5. Architectural Bottlenecks (ranked by impact on the actual goal)

1. **Execution fidelity.** Synthetic events + CSS selectors + no shadow/iframe support is the single biggest limiter of real task completion. SOTA-level reliability needs CDP-level trusted input (via `chrome.debugger` in-extension, or Playwright-over-the-user-session via CDP attach) and a more robust locator/vision strategy.
2. **No closed-loop autonomy or replanning in the live path.** The product cannot recover from a wrong step except by asking the human and re-extracting. The recovery/adaptive code that would help is in the unused stack.
3. **Perception is text-only in the loop.** Visually-defined controls, canvas apps, and map/date widgets are effectively invisible. Vision is only used on a keyword-detected "extraction task" branch, controlled by brittle string matching (`"section 10"`, `"section 19"`).
4. **Two-codebase divergence (effort sink).** ~80% of the code (and tests) is the orphaned heuristic platform. Every hour spent there is an hour not spent closing the execution-fidelity gap. This is the dominant *organizational* bottleneck.
5. **In-memory volatile state.** Every registry is a process-local TTL dict; `persistence.py` is stubbed. The "platform" loses all mission/trust/governance/approval state on restart and cannot scale beyond one process — so even if it were wired in, it isn't production-viable as written.
6. **Single Gemini call per step, no streaming, no caching.** Linear token/latency cost; ADR-007 (no SSE) and the absence of prompt caching make long workflows slow and expensive.

---

## 6. Scalability & Future-Proofing

- **Horizontal scale is blocked** by in-memory singletons guarded by `threading.RLock()` (state is per-process, not shared). Anything beyond single-user localhost requires real persistence and externalized state — currently stubs.
- **Provider coupling.** `ai_service` hardwires Gemini + OpenRouter request/parse logic, with JSON-repair and fence-stripping baked in. No model-agnostic abstraction; migrating to a stronger agentic model (e.g., tool-use / structured output / vision) means surgery in one large module.
- **Prompt brittleness.** The single 150-line system prompt + regex JSON extraction + keyword-driven clarification suppression is doing a lot of load-bearing work. This is fragile against model upgrades and new sites.
- **Cost/latency trajectory.** Without streaming, prompt caching, or multi-step planning, per-task cost grows with workflow length precisely on the long flows the product targets.
- **The milestone process scales the wrong dimension.** Each new "version" adds breadth (a new subsystem) rather than depth (loop reliability), so future-proofing is getting *worse* per milestone: more surface to maintain, no closer to the goal.

---

## 7. Maintenance & Technical-Debt Trajectory

- **~77 near-identical scaffold files** (11 subsystems × 6–7 of `models/registry/persistence/analytics/timeline/inspector/generator`). High duplication, low information density. A single generic TTL-registry base + shared event/timeline bus would collapse most of it.
- **Test mass is misleading.** ~180 test files / ~29.5k lines, but the bulk assert in-memory round-trips of the orphaned components; the 19 benchmarks measure sub-millisecond heuristic latency. **No test or benchmark measures real task-completion rate on the target workflows** — the only metric that matters for this product. Real-browser tests skip silently because Playwright isn't a declared dependency.
- **Documentation drift.** `docs/architecture.md` and `docs/roadmap.md` describe the original 7-phase Gemini MVP and are now badly out of date relative to the code; `decisions.md` ADR-006 is contradicted by the (unused) Playwright gateway. Newcomers will be misled about what runs.
- **Scratch/benchmark/validate sprawl** (`scratch/`, `benchmark_v*.py`, `validate_v*.py`, `debug_*.json`) is committed at the repo root and inflates cognitive load.
- **Net:** maintenance cost is already high and compounding, while the maintained code is mostly not in the product.

---

## 8. What Is Genuinely Good (keep these)

- The **safety model**: per-action human approval, server-side action allowlist enforced regardless of model output, danger/caution classification, PII redaction at extraction, keys server-only.
- The **real-session insight**: operating in the user's authenticated Chrome is the right product bet and a real moat vs. managed-browser agents.
- The **live-loop support modules**: context compression, grounded element registry, verified-facts state, budget enforcement, and replay timeline are sensible and reasonably implemented.
- **Code quality in isolation** is high — clear modules, typed models, thorough unit tests. The problem is allocation and integration, not craftsmanship.

---

## 9. Strategic Recommendations (prioritized)

### P0 — Stop the divergence; refocus on the loop that ships
- **Freeze the V*/Phase milestone factory.** No new parallel subsystem until it is wired into the live `/analyze` loop and improves a real task-success metric.
- **Pick one execution model.** Recommend: keep the user's-session advantage and upgrade in-extension execution to **trusted input via `chrome.debugger`/CDP** (Input.dispatchMouseEvent/keyboard), or attach Playwright to the user's Chrome over CDP. Either way, **retire the standalone server-side Playwright Chromium** — it can't be logged in and duplicates the loop.

### P0 — Establish the only metric that matters
- Build a **task-success harness** over the 10 target workflows (recorded/deterministic mirrors where possible) reporting step-success and end-to-end completion rate. Make this the milestone gate, replacing the structural `validate_v*` checks.

### P1 — Close the execution-fidelity gap
- Add **shadow-DOM and iframe traversal** to the extractor; replace synthetic `.click()`/value-set with trusted CDP input; harden the locator strategy (prefer role+name, text, and stable attributes; add a fallback ladder).
- Add **vision into the live loop** (screenshot + set-of-marks) for visually-defined controls, not just the keyword-gated extraction branch.

### P1 — Make the loop a real agent loop
- Introduce **bounded multi-step planning + failure-driven replanning** so the system can recover without a human round-trip on every step, while keeping the approval gate for risky/destructive actions only. Reuse the existing deterministic `failure_classes`/`recovery` logic — but in the live path.

### P2 — Pay down debt and align docs
- Collapse the ~77 scaffold files into a shared registry/timeline/analytics base; **delete or quarantine the orphaned subsystems** that won't be wired soon (move to a clearly-labeled `experimental/` area rather than `main.py`).
- If any of the platform state is to be kept, implement **real persistence** (the DB exists) and remove the stub `persistence.py` modules.
- **Rewrite `docs/architecture.md`/`roadmap.md`/`decisions.md`** to describe what actually runs; add an ADR recording the execution-model decision above.
- Move `scratch/`, `benchmark_*`, `validate_*`, `debug_*.json` out of the tracked root.

### P2 — Provider & cost posture
- Introduce a **model-agnostic agent interface** (tool-use/structured-output/vision capable) so the loop can adopt the strongest available model without rewriting `ai_service`.
- Add **prompt caching** for the stable system prompt and **streaming** for responsiveness on long flows.

---

## 10. Target Architecture (one-paragraph north star)

A single closed-loop agent running inside the user's authenticated Chrome: a vision+a11y perception layer that pierces shadow/iframe boundaries, a model-agnostic planner that decomposes the task and replans on failure, CDP-level trusted execution, an approval gate scoped to risky actions, and a small persisted state/memory store. The deterministic guards (risk classification, allowlist, budget) survive as thin safety rails around that loop — not as a 30-subsystem parallel platform. Success is measured by completion rate on the 10 target workflows, and milestones deepen that loop rather than widen the scaffolding.
