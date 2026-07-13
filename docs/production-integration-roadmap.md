# Production Integration Roadmap

Date: 2026-07-12

Scope: production integration plan only. This roadmap uses repository evidence and the Benchmark-to-Production Gap Analysis to sequence the minimum work needed to bring proven benchmark intelligence into the real Chrome Extension browser assistant. It does not introduce new architecture, benchmark scenarios, or benchmark-only milestones.

## 1. Integration Principles

1. Reuse the production workflow as the spine.

   The existing product path already runs through `extension/src/sidepanel/hooks/useWorkflow.ts`, `extension/src/background/service-worker.ts`, `backend/app/api/routes/analyze.py`, `backend/app/orchestrator/workflow_orchestrator.py`, `backend/app/context_compression/*`, and `backend/app/services/ai_service.py`. Integration should deepen this path instead of creating another controller.

2. Promote benchmark-proven logic only when the production loop has a consumer.

   Benchmark capabilities should move into production only when a real user workflow can consume their decision. For example, Goal Convergence is useful only after production has semantic signatures and a Continue vs Complete decision point.

3. Do not duplicate planner, validator, or recovery roles.

   The LLM in `ai_service.py` remains the planner. Validation remains the completion authority. Recovery remains an orchestration policy that changes the next planner turn's context, not a second planner.

4. Integrate in dependency order.

   Planner Contract V2 outcome handling must land before Report verification. Semantic signatures must land before Goal Convergence. Goal Convergence must land before Strategy Generation and Planner Recovery.

5. Keep extension and backend responsibilities clear.

   The extension owns page extraction, user/auto approval, content-script execution, and UI state. The backend owns planner request construction, compressed context, persisted workflow/session facts, and provider parsing. Completion/recovery decisions should be surfaced across that boundary without creating conflicting logic on both sides.

6. Preserve current product behavior until a stronger decision replaces it.

   Existing behaviors such as manual approval, Auto mode, re-analysis after each step, and extension progress checks should remain intact while benchmark capabilities are integrated around them.

## 2. Integration Order

| Capability | Decision | Repository evidence | Rationale |
|---|---|---|---|
| Context Compression | Integrate now: already production path | `WorkflowOrchestrator.orchestrate_analysis()` instantiates `ContextCompressor` and passes `compressed_context` to `ai_service.analyze()`. | This is already production-ready. Future product work should reuse it rather than bypass it. |
| Planner Contract V2 | Integrate now | Backend `AnalyzeResponse` includes `outcome_kind`, `report`, and `replan` in `backend/app/schemas/response.py`; `ai_service.py` prompts/parses these fields. Extension `AnalyzeResponse` omits them and `useWorkflow.ts` only branches on `clarification_question` and `suggested_actions`. | Production cannot safely use SGV, Report completion, or Replan until the extension/controller understands Planner Contract V2 outcomes. |
| Planner Traceability | Integrate now, lightly | `/analyze` accepts `X-Trace-Id`; `ai_service.py` records provider exchanges when `TRACE_MODE` is enabled; benchmark traces are assembled by `backend/benchmark/trace/recorder.py`. Extension does not send trace ids. | Low behavioral risk and high debugging value. It makes production failures evidence-driven before deeper autonomy lands. |
| Semantic Signatures | Integrate now after Planner Contract V2 | Benchmark signatures live in `TaskRunner._semantic_signature()` and `_semantic_texts()`; production has only `contextFingerprint()` in `useWorkflow.ts`. Extraction already captures needed form state in `extractor_v2.ts`. | Needed for production Goal Convergence and for distinguishing real progress from loops. |
| Semantic Goal Validation | Integrate now after Planner Contract V2 | Benchmark completion uses success criteria in `m0_task_runner.py`; production has no completion authority beyond no actions, user stop, and simple progress checks. | The assistant needs verified completion, especially for Report outcomes and information extraction tasks. |
| Goal Convergence | Integrate later, after semantic signatures and SGV | `GoalConvergenceEngine` is benchmark-only. Production repeated-action logic suppresses identical actions but does not compare semantic/validation signatures. | Valuable only once production has semantic progress and validation signals. |
| Strategy Generation | Integrate later, after Goal Convergence | Benchmark `strategy_generation.py` formats convergence evidence into prior-step context. Production `buildPriorSteps()` only serializes completed actions/results/page snapshots. | It depends on convergence evidence. Adding it earlier would add context without a reliable trigger. |
| Planner Recovery | Integrate later, after Strategy Generation | Benchmark recovery mode is one-turn prior-step injection in `TaskRunner._planner_prior_steps()`. Production has no recovery-mode state. | It depends on Goal Convergence and Strategy Generation context. |

No listed capability should remain permanently benchmark-only. The only keep-benchmark-only role is the benchmark harness itself: reports, scenarios, Playwright driver, trace viewer, and scoring remain evaluation infrastructure, not product behavior.

## 3. Production Milestones

### PI-1: Planner Contract V2 Consumption In The Extension

Objective:

- Make the production workflow consume the backend Planner Contract V2 response shape without changing planner behavior.

Existing capability integrated:

- Planner Contract V2.

Expected production touchpoints:

- `extension/src/types/index.ts`
- `extension/src/sidepanel/hooks/useWorkflow.ts`
- Existing backend response from `backend/app/schemas/response.py`

Repository evidence:

- Backend already emits `outcome_kind`, `report`, and `replan`.
- Extension currently discards these fields by type and control flow.

Production behavior after milestone:

- `act` and `wait` continue through the existing action approval/execution path.
- `ask` routes to the existing `needs_input` UI.
- `report` can be displayed as a report outcome but should not self-certify completion until validation is integrated.
- `replan` can be preserved as planner state/context instead of being treated as generic "no action".

### PI-2: Production Planner Traceability

Objective:

- Let normal Chrome Extension runs capture enough planner request/response evidence when tracing is enabled.

Existing capability integrated:

- Planner Traceability.

Expected production touchpoints:

- Extension request path in `useWorkflow.ts`
- `/analyze` trace header support in `backend/app/api/routes/analyze.py`
- Existing provider trace sink in `ai_service.py`
- Existing workflow/session logging as the production artifact surface

Repository evidence:

- `/analyze` already accepts `X-Trace-Id`.
- `ai_service.py` already records provider exchanges when `TRACE_MODE` is enabled.
- Benchmark traceability proves the fields needed for investigation.

Production behavior after milestone:

- A user or developer can reconstruct what the planner received and returned for a real extension workflow, without running the benchmark.

### PI-3: Production Semantic Signature

Objective:

- Give the production loop a stable semantic progress signal using already-extracted page representation.

Existing capability integrated:

- Semantic Signatures.

Expected production touchpoints:

- Existing page context from `extractor_v2.ts`
- Production workflow state in `useWorkflow.ts` or backend session state in `WorkflowOrchestrator`
- Benchmark semantic text rules from `TaskRunner._semantic_texts()` as reusable logic, not benchmark runner control flow

Repository evidence:

- `extractor_v2.ts` captures visible text, content blocks, headings, selected text, form values, selected options, checkbox state, and password filled state.
- Benchmark semantic signatures already use these signals.
- Production `contextFingerprint()` is a coarser string over URL/title/headings/visible text/elements/content blocks and does not include all semantic form state.

Production behavior after milestone:

- The assistant can tell that filling a form field, selecting an option, or checking a box is semantic progress.
- The assistant is less likely to stop or replan during productive form workflows.

### PI-4: Production Semantic Goal Validation

Objective:

- Add a production completion authority so workflows terminate because the user's goal is satisfied, not merely because actions stopped.

Existing capability integrated:

- Semantic Goal Validation.

Expected production touchpoints:

- Production workflow controller around `useWorkflow.ts` and/or `WorkflowOrchestrator`
- Current page context
- Planner `report` payload
- Existing verified facts/state where applicable

Repository evidence:

- Benchmark SGV verifies Report completion by evaluating current evidence before terminating.
- Production currently marks `complete` when `allowedActions.length === 0`, or when the user stops, without a validation authority.

Production behavior after milestone:

- Information-seeking tasks can complete with a verified answer.
- Unsupported reports continue instead of falsely completing.
- The planner never self-certifies success.

### PI-5: Production Goal Convergence

Objective:

- Detect when the production workflow is no longer making semantic progress toward the user goal.

Existing capability integrated:

- Goal Convergence.

Expected production touchpoints:

- Semantic signatures from PI-3
- Validation state from PI-4
- Prior step history already built by `buildPriorSteps()`

Repository evidence:

- Benchmark `GoalConvergenceEngine` consumes semantic and validation signatures.
- Production repeated-action handling only checks action signatures and repeated failures/successes.

Production behavior after milestone:

- The assistant can stop blindly repeating clicks, waits, or reports when evidence does not change.
- The user sees fewer loops and fewer "stopped because repeated action" dead ends.

### PI-6: Production Strategy Generation Context

Objective:

- When Goal Convergence fires, pass structured evidence about the failed strategy into the next planner request.

Existing capability integrated:

- Strategy Generation.

Expected production touchpoints:

- Prior-step construction in `useWorkflow.ts` or backend orchestrator context construction
- Existing Strategy Generation context format from benchmark
- Current page context and validation/convergence evidence

Repository evidence:

- Benchmark `strategy_generation.py` does not plan; it formats expected goal, observed evidence, contradiction, failed strategy, avoid-next guidance, validation misses, and convergence reason.
- Production prior steps currently contain only executed actions, results, optional analysis snapshot, and page snapshot.

Production behavior after milestone:

- The planner receives explicit evidence explaining why the previous strategy failed.
- The next planner call has a better chance of choosing a different strategy without introducing a second planner.

### PI-7: Production Planner Recovery

Objective:

- Mark exactly one production planner turn as a recovery planning cycle after Goal Convergence and Strategy Generation.

Existing capability integrated:

- Planner Recovery.

Expected production touchpoints:

- Production workflow state machine in `useWorkflow.ts`
- Prior-step payload sent to `/analyze`
- Existing backend planner prompt path through compressed context

Repository evidence:

- Benchmark recovery is a lightweight one-turn policy in `TaskRunner._planner_prior_steps()`.
- Production has re-analysis after failure but no explicit recovery turn.

Production behavior after milestone:

- The assistant enters a visible recovery planning cycle instead of behaving like normal continuation after non-progress.
- Recovery state clears after one planner response, avoiding persistent mode drift.

## 4. Dependency Graph

```text
Existing production workflow
  |
  +--> Context Compression already integrated
  |
  +--> PI-1 Planner Contract V2 Consumption
  |       |
  |       +--> PI-4 Semantic Goal Validation
  |       |
  |       +--> Report / Ask / Replan UI semantics
  |
  +--> PI-2 Planner Traceability
  |       |
  |       +--> Evidence-driven production debugging
  |
  +--> PI-3 Semantic Signature
          |
          +--> PI-4 Semantic Goal Validation
                  |
                  +--> PI-5 Goal Convergence
                          |
                          +--> PI-6 Strategy Generation Context
                                  |
                                  +--> PI-7 Planner Recovery
```

Minimum dependency order:

1. PI-1 and PI-2 can proceed first.
2. PI-3 should precede PI-5.
3. PI-4 requires PI-1 and benefits from PI-3.
4. PI-5 requires PI-3 and PI-4.
5. PI-6 requires PI-5.
6. PI-7 requires PI-6.

## 5. Expected User Impact

| Milestone | User-visible capability gained |
---|---|
| PI-1 Planner Contract V2 Consumption | The assistant can distinguish taking an action, answering from the page, waiting, asking the user, and replanning. Reports no longer look like silent "no action needed" endings. |
| PI-2 Planner Traceability | When a real workflow behaves badly, the exact planner input and output can be inspected. This reduces guesswork when fixing production issues. |
| PI-3 Semantic Signature | The assistant better recognizes progress in real forms and pages, including filled fields, selected options, checkboxes, and visible semantic changes. |
| PI-4 Semantic Goal Validation | The assistant completes when the user goal is actually satisfied, especially for tasks like "tell me the total", "read this value", or "confirm the status". |
| PI-5 Goal Convergence | The assistant detects non-progress earlier and avoids repeated clicks, waits, or unsupported reports. |
| PI-6 Strategy Generation Context | After a stalled strategy, the assistant gives the planner concrete evidence about what failed, leading to more useful next attempts. |
| PI-7 Planner Recovery | The assistant performs a real recovery planning turn after non-progress instead of treating failure as ordinary continuation. |

## 6. MVP Completion Assessment

The minimum integration point at which the browser assistant becomes a practical MVP is after PI-4: Planner Contract V2 consumption, production traceability, semantic signatures, and Semantic Goal Validation.

Repository evidence:

- The current extension already supports real user workflows: page extraction, backend planning, approval/Auto mode, content-script execution, DOM settle waits, progress checks, and re-analysis.
- Backend Context Compression and Planner Contract V2 parser support already exist.
- The critical missing product behavior is verified completion. Today, `useWorkflow.ts` treats empty allowed actions as `complete`, while benchmark SGV proved that Report completion must be validated against current semantic evidence.
- Without PI-4, the assistant can act and reanalyze, but it cannot reliably know when the user's original goal has been achieved.
- With PI-4, the assistant becomes useful for a practical MVP class of real tasks: navigate, fill, click, extract visible information, and stop on verified completion.

Goal Convergence, Strategy Generation, and Planner Recovery remain important for stronger autonomy, but they are not the minimum MVP line. They improve resilience after the assistant is already capable of understanding Planner Contract V2 outcomes and validating completion.
