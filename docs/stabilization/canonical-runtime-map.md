# Canonical Client MVP Runtime Map

**Canonical backend:** `http://localhost:8000`  
**Extension build:** `extension/dist`  
**Launcher:** `scripts/start-stabilization-runtime.ps1`  
**Execution rule:** One backend listener, one compiled backend URL, one visible runtime identity.

## Live request and execution path

```text
User
  -> extension/src/sidepanel/App.tsx
  -> extension/src/sidepanel/hooks/useWorkflow.ts
  -> extension service worker: EXTRACT_CONTEXT
  -> extension/src/content/extractor.ts + extractor_v2.ts
  -> POST http://localhost:8000/analyze
  -> backend/app/api/routes/analyze.py
  -> backend/app/orchestrator/workflow_orchestrator.py
  -> backend/app/services/ai_service.py or deterministic observed-control path
  -> side-panel approval/auto gate
  -> extension service worker: EXECUTE_ACTION
  -> POST http://localhost:8000/policy/enforce
  -> backend/app/policy/live_engine.py
  -> one bound-tab execution dispatch
  -> DOM/widget fast path, then trusted CDP fallback for eligible safe no-effects
  -> extension/src/content/action_verification.ts
  -> extension/src/sidepanel/hooks/useWorkflow.ts observe/replan/complete loop
  -> extension/src/sidepanel/durableWorkflowLedger.ts checkpoint
  -> backend workflow/mission/policy audit persistence
```

## Canonical component ownership

| Concern | Authoritative production component | Responsibility |
|---|---|---|
| Side-panel workflow state | `extension/src/sidepanel/hooks/useWorkflow.ts` | Observe/plan/approve/execute/verify loop |
| Visible runtime identity | `extension/src/sidepanel/App.tsx` | Refuse silent version/build/URL drift |
| Backend URL and build constants | `extension/src/config.ts` | Single compiled endpoint and extension identity |
| Privileged browser entry | `extension/src/background/service-worker.ts` | Sender/tab binding, policy, dispatch, adapter trace |
| Page observation | `extension/src/content/extractor.ts`, `extractor_v2.ts` | Compact DOM/a11y/text/control state |
| Planning/orchestration | `backend/app/orchestrator/workflow_orchestrator.py` | Deterministic actions, planner context and outcomes |
| Live policy | `backend/app/policy/live_engine.py` via `/policy/enforce` | Allow/confirm/deny immediately before mutation |
| DOM execution | `extension/src/content/executor.ts`, `executor_v2.ts` | Fast semantic actions where browser trust is unnecessary |
| Trusted input | `extension/src/background/cdp_control.ts` | Bound-tab CDP mouse/keyboard input and grounding |
| Upload/download | `extension/src/content/file_transfer.ts`, service worker download watcher | Approved file and download lifecycle evidence |
| Verification | `extension/src/content/action_verification.ts` | Structured effect/no-effect/uncertain result |
| Durable recovery | `extension/src/sidepanel/durableWorkflowLedger.ts` | Idempotency, restart state and uncertainty boundary |
| Server audit/state | PostgreSQL models and workflow/mission/policy services | Session, action, policy and mission evidence |

## Runtime identity contract

The launcher creates one build identity and supplies it to both sides:

- `app_version`
- `build_commit`
- `build_id`
- `canonical_backend_url`
- backend process ID

The backend returns these fields from `/health`. The side panel displays `Runtime OK`, `RUNTIME MISMATCH`, or `BACKEND OFFLINE`. A baseline is invalid unless the visible state is `Runtime OK`.

## Excluded evidence paths

The following do not count as the client MVP production path:

- `backend/benchmark` runners and synthetic executors;
- Phase capability metadata marked `shadow`, `experimental`, `stub`, or `dead`;
- standalone Playwright success that bypasses the side-panel execution loop;
- direct website manipulation used only for read-only recovery inspection;
- mocks or controlled fixture results presented as third-party workflow completion.

## Process invariant

The guarded launcher:

1. refuses listeners on alternate validation ports `8001`–`8003`;
2. refuses more than one listener on `8000`;
3. reuses an existing listener only if its health identity and process ID match;
4. builds `extension/dist` and starts non-reloading Uvicorn with the same build identity;
5. writes the active identity to `docs/production_validation/day1/runtime/runtime-latest.json`.
