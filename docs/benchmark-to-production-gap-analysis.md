# Benchmark To Production Gap Analysis

Date: 2026-07-12

Scope: audit of repository wiring only. This document does not propose new architecture or benchmark changes. It identifies which benchmark capabilities are already used by the normal Chrome Extension workflow and which remain benchmark-only.

## 1. Current Production Workflow

The normal browser assistant flow is the Chrome Extension side panel flow, not the benchmark runner.

```text
User
  ↓
Extension Side Panel
  extension/src/sidepanel/App.tsx
  extension/src/sidepanel/hooks/useWorkflow.ts
  ↓
Background Service Worker
  extension/src/background/service-worker.ts
  ↓
Content Extraction
  extension/src/content/extractor.ts
  extension/src/content/extractor_v2.ts
  ↓
POST /analyze
  backend/app/api/routes/analyze.py
  ↓
Production WorkflowOrchestrator
  backend/app/orchestrator/workflow_orchestrator.py
  ↓
ContextCompressor
  backend/app/context_compression/compressor.py
  backend/app/context_compression/relevance_ranker.py
  backend/app/context_compression/state_summarizer.py
  ↓
AI Planner
  backend/app/services/ai_service.py
  ↓
AnalyzeResponse
  backend/app/schemas/response.py
  ↓
Extension Side Panel Action Gate
  extension/src/sidepanel/hooks/useWorkflow.ts
  ↓
User approval or Auto mode approval
  extension/src/sidepanel/App.tsx
  ↓
Background Service Worker
  extension/src/background/service-worker.ts
  ↓
Content Execution
  extension/src/content/executor.ts
  extension/src/content/executor_v2.ts
  ↓
Extension-level progress check
  extension/src/sidepanel/hooks/useWorkflow.ts
  ↓
Re-analyze or stop
```

Production behavior evidence:

- The side panel calls `EXTRACT_CONTEXT`, then posts `session_id`, `task`, `page_context`, and optional `prior_steps` to `http://localhost:8000/analyze` in `extension/src/sidepanel/hooks/useWorkflow.ts`.
- The service worker handles `EXTRACT_CONTEXT`, `EXECUTE_ACTION`, `WAIT_FOR_TAB_LOAD`, and `WAIT_FOR_DOM_SETTLE` in `extension/src/background/service-worker.ts`.
- The backend route delegates to `WorkflowOrchestrator.orchestrate_analysis()` in `backend/app/api/routes/analyze.py`.
- `WorkflowOrchestrator` registers elements, loads persisted verified facts, builds compressed context, calls `ai_service.analyze()`, records budget/analytics, and returns the result. It does not execute browser actions, validate task success criteria, run Goal Convergence, Strategy Generation, or Planner Recovery.
- The extension executes actions itself through content scripts after approval. It then re-extracts the page and calls `/analyze` again.

## 2. Benchmark Components

| Component | Used in Production? | Where? | Evidence |
|---|---:|---|---|
| Planner Contract V2 | Partially | Backend schema and parser only | `backend/app/schemas/response.py` defines `outcome_kind`, `report`, and `replan`; `backend/app/services/ai_service.py` prompts for `act/report/wait/ask/replan` and parses them. The extension type `extension/src/types/index.ts` does not include `outcome_kind`, `report`, or `replan`, and `useWorkflow.ts` only branches on `clarification_question` and `suggested_actions`. |
| Semantic Goal Validation (SGV-1, SGV-2) | No | Benchmark runner only | Verified Report completion is implemented in `backend/benchmark/m0_task_runner.py` by evaluating benchmark success criteria after `outcome_kind == "report"`. Production `WorkflowOrchestrator.orchestrate_analysis()` returns the planner response directly and has no success-criteria evaluator. |
| Goal Convergence | No | Benchmark runner only | `backend/benchmark/goal_convergence.py` is imported and instantiated by `backend/benchmark/m0_task_runner.py`. No production import of `GoalConvergenceEngine` exists under `backend/app` or `extension/src`. |
| Strategy Generation | No | Benchmark runner only | `backend/benchmark/strategy_generation.py` is called by `TaskRunner._append_convergence_replan()` in `backend/benchmark/m0_task_runner.py`. No production import exists under `backend/app` or `extension/src`. |
| Planner Recovery | No | Benchmark runner only | Recovery-mode context is injected by `TaskRunner._planner_prior_steps()` in `backend/benchmark/m0_task_runner.py` after Goal Convergence. Production has no equivalent recovery-mode flag or one-turn recovery cycle. |
| Context Compression | Yes | Production backend `/analyze` path | `backend/app/orchestrator/workflow_orchestrator.py` instantiates `ContextCompressor` and passes `compressed_context` into `ai_service.analyze()`. The recent `relevant_visible_content` improvement is in `backend/app/context_compression/compressor.py`, so it is production-path code. |
| Improved Semantic Signatures | Benchmark only | Benchmark validation/convergence path | Semantic signatures are computed by `TaskRunner._semantic_signature()` and `_semantic_texts()` in `backend/benchmark/m0_task_runner.py`. Production has `contextFingerprint()` and repeated-action guards in `extension/src/sidepanel/hooks/useWorkflow.ts`, but it does not use the benchmark semantic signature or criterion signature. |
| Planner Traceability | Benchmark only, backend provider trace gated | Benchmark trace recorder plus optional backend trace sink | `backend/benchmark/trace/recorder.py` assembles benchmark step traces. `backend/app/api/routes/analyze.py` accepts `X-Trace-Id`, and `ai_service.py` records provider exchanges when `TRACE_MODE` is enabled, but the normal extension does not send `X-Trace-Id` and does not create benchmark trace artifacts. |

## 3. Missing Integrations

### Semantic Goal Validation

Benchmark-only reason:

- SGV is represented in benchmark code as task success-criteria evaluation in `backend/benchmark/criteria.py` and `backend/benchmark/m0_task_runner.py`.
- Production `/analyze` has no task definition, success criteria, benchmark `EvalContext`, or completion authority.

Production layer that would consume it:

- The production workflow controller around `/analyze` and extension re-analysis would need to consume a goal validation result before deciding whether to continue, complete, or ask the user.

### Verified Report Completion

Benchmark-only reason:

- The positive Report path is handled in `backend/benchmark/m0_task_runner.py` when `outcome_kind == "report"`.
- Production backend can return `report`, but production extension ignores the `report` payload because `extension/src/types/index.ts` omits it and `useWorkflow.ts` treats empty `suggested_actions` as "complete" without validation.

Production layer that would consume it:

- The production orchestrator or extension workflow loop would need to verify report claims against current page evidence before showing completion.

### Goal Convergence

Benchmark-only reason:

- The engine lives in `backend/benchmark/goal_convergence.py`.
- It consumes benchmark semantic signatures and validation signatures produced by `TaskRunner`.
- Production has a simpler repeated-action filter in `extension/src/sidepanel/hooks/useWorkflow.ts`, but that filter only suppresses repeated next actions; it does not reason over semantic progress or validation state.

Production layer that would consume it:

- The production loop that decides whether to send another `/analyze` call would consume convergence evidence from prior steps, current page context, and validation status.

### Strategy Generation

Benchmark-only reason:

- Strategy context is generated by `backend/benchmark/strategy_generation.py` and appended to benchmark `prior_steps`.
- Production `buildPriorSteps()` in `extension/src/sidepanel/hooks/useWorkflow.ts` only serializes completed actions, execution results, optional analysis snapshots, and page snapshots.

Production layer that would consume it:

- The production prior-step builder or backend orchestrator would need to include the existing recovery context as planner context after convergence.

### Planner Recovery

Benchmark-only reason:

- Planner Recovery Phase 1 is expressed as a one-turn prior-step injection inside `TaskRunner._planner_prior_steps()`.
- Production has execution retry/re-analysis and repeated-action suppression, but no explicit recovery planning mode.

Production layer that would consume it:

- The production workflow controller would need to mark one planner invocation as a recovery turn after convergence and then clear that state.

### Semantic Signatures

Benchmark-only reason:

- Benchmark semantic signatures include visible text, content blocks, headings, selected text, input values, selected options, password filled state, and checkbox checked state via `TaskRunner._semantic_texts()`.
- Production extraction captures form state in `extension/src/content/extractor_v2.ts`, but production does not compute or persist the benchmark semantic signature.

Production layer that would consume it:

- The production loop would consume semantic signatures to distinguish real page progress from repeated non-progress.

### Planner Traceability

Benchmark-only reason:

- Trace artifacts are assembled by `backend/benchmark/trace/recorder.py`.
- Production `/analyze` supports trace recording only when `TRACE_MODE` and `X-Trace-Id` are present.
- The extension does not send trace ids, does not persist planner request/response traces, and does not expose trace artifacts.

Production layer that would consume it:

- The production workflow run/session logging layer would consume trace ids and persist planner request/response records for debugging.

## 4. Integration Dependencies

| Missing capability | Prerequisite components | Downstream consumers | Dependency chain |
|---|---|---|---|
| SGV | Current page context; task goal; success criteria or equivalent goal evidence; planner analysis/report | Production workflow completion decision | Extension/backend observe page -> validation evidence -> completion/continue decision |
| Verified Report Completion | Planner Contract V2 `report`; SGV evidence; current page context | Extension completion UI; workflow session status | Planner returns Report -> validation verifies/refutes -> workflow completes or continues |
| Goal Convergence | Semantic signature; validation signature; prior step history | Planner Recovery and Strategy Generation | Observe -> validate -> signature comparison -> convergence decision |
| Strategy Generation | Goal Convergence decision; validation failures; page context; prior strategy evidence | Next planner invocation context | Convergence fires -> strategy context appended to prior steps -> planner receives context |
| Planner Recovery | Goal Convergence + Strategy Generation context | Next `/analyze` call | Convergence fires -> recovery-mode prior step -> one planner turn -> recovery state clears |
| Semantic Signatures | Extracted representation from extension; content blocks; element state; page text | Goal Convergence; validation diagnostics | Extract page -> build signature -> compare across steps |
| Planner Traceability | Trace id propagation; request/response persistence; provider trace sink | Debugging and benchmark/product parity analysis | Extension/backend run id -> `/analyze` trace id -> provider trace -> workflow trace artifact |

## 5. MVP Readiness

| Capability | Classification | Evidence |
|---|---|---|
| Context Compression | Production Ready | Used directly by `WorkflowOrchestrator.orchestrate_analysis()` before every production planner call. |
| Planner Contract V2 backend schema/parser | Partially Integrated | Backend supports it, but extension workflow ignores `outcome_kind`, `report`, and `replan`. |
| Form-state extraction for semantic evidence | Partially Integrated | `extractor_v2.ts` captures value, selected text, checkbox checked, and password filled state; production does not use benchmark semantic signatures. |
| Planner Traceability | Partially Integrated | Backend trace sink exists behind `TRACE_MODE` and `X-Trace-Id`; extension does not participate. |
| SGV-1/SGV-2 | Benchmark Only | Completion validation exists in benchmark runner, not production orchestrator or extension loop. |
| Goal Convergence | Benchmark Only | Implemented in `backend/benchmark/goal_convergence.py`; not imported by production path. |
| Strategy Generation | Benchmark Only | Implemented in `backend/benchmark/strategy_generation.py`; not imported by production path. |
| Planner Recovery | Benchmark Only | Implemented as benchmark prior-step policy in `backend/benchmark/m0_task_runner.py`; not production path. |
| Benchmark semantic signatures | Benchmark Only | Computed inside `TaskRunner`; production has a different `contextFingerprint()` repeated-action guard. |

## 6. Highest-Impact Remaining Product Work

This ranking includes only product-level integration work that moves the actual Chrome Extension workflow toward autonomous browser assistance. It excludes benchmark-only improvements.

1. Integrate Planner Contract V2 outcomes into the extension workflow.
   - Evidence: backend `AnalyzeResponse` includes `outcome_kind/report/replan`, but extension `AnalyzeResponse` does not. `useWorkflow.ts` treats no allowed action as completion or needs input without understanding Report or Replan.
   - Product impact: production currently cannot correctly distinguish "answer/report", "ask", "replan", "wait", and "act" at the UI/controller level.

2. Add production goal validation/completion authority.
   - Evidence: benchmark completion is success-criteria driven in `m0_task_runner.py`; production has only extension progress checks and repeated-action suppression.
   - Product impact: without validation, the browser assistant terminates based on absence of actions or user stops, not verified goal satisfaction.

3. Integrate semantic progress tracking into the production loop.
   - Evidence: benchmark semantic signatures detect progress/non-progress using page text, content blocks, and form state; production only uses `contextFingerprint()` and repeated action signatures.
   - Product impact: production cannot reliably tell productive form progress from non-progress, or unsupported reports from verified completion.

4. Integrate Goal Convergence, Strategy Generation, and Planner Recovery into the production control loop.
   - Evidence: these capabilities are benchmark modules and prior-step policies inside `TaskRunner`. Production prior steps are built only from completed actions and execution results.
   - Product impact: production can reanalyze after failure, but it does not explicitly enter a recovery planning cycle after semantic stagnation.

5. Add production planner trace propagation.
   - Evidence: backend trace support exists, but extension does not send `X-Trace-Id`; benchmark trace reconstruction is outside normal product usage.
   - Product impact: production debugging cannot yet reconstruct the exact planner input/output chain available in benchmark investigations.

## 7. Final Recommendation

If the goal is a working autonomous browser assistant, effort should now shift primarily toward integrating the benchmark-proven capabilities into the production workflow.

Repository evidence supports this:

- The production Chrome Extension loop already performs real extraction, backend planning, user/auto approval, content-script execution, and re-analysis.
- The backend production planner already has Context Compression and Planner Contract V2 schema/parser support.
- The benchmark loop now contains the stronger autonomy controls: SGV, verified Report completion, semantic signatures, Goal Convergence, Strategy Generation, Planner Recovery, and traceability.
- Those controls are mostly absent from `extension/src/sidepanel/hooks/useWorkflow.ts` and `backend/app/orchestrator/workflow_orchestrator.py`.

Continuing primarily in the benchmark would improve measured benchmark behavior but would not by itself make the real Chrome Extension assistant more autonomous. The largest product gap is no longer lack of benchmark evidence; it is that the production workflow has not consumed the benchmark loop's validation, convergence, and recovery decisions.
