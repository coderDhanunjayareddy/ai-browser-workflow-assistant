# V3 Implementation Specification

Date: 2026-07-21

Status: production implementation specification. This document is the technical contract for implementing the revised V3 architecture. It does not implement code.

## 1. Scope

V3 upgrades the existing production browser assistant without rewriting it.

Preserve:

- Chrome Extension MV3 production loop.
- FastAPI backend.
- Planner Contract V2 during foundation migration.
- Existing execution engine.
- Existing SGV, Goal Convergence, Strategy Generation, Planner Recovery concepts.
- Existing benchmark and production validation assets.

Introduce:

- versioned data contracts;
- feature flags;
- canonical run ledger;
- production trace parity;
- deterministic semantic page graph;
- capability registry;
- layered planner packet;
- semantic target and grounding model;
- mission FSM;
- general validation object;
- world model and reasoning memory;
- unified policy and recovery policy;
- performance and observability budgets.

## 2. Repository Structure

New backend modules:

```text
backend/app/run_ledger/
  models.py
  writer.py
  reader.py
  projections.py
  migrations.py

backend/app/contracts/
  versions.py
  planner_packet.py
  ledger_events.py
  semantic_graph.py
  mission_state.py
  validation.py
  capabilities.py
  world_model.py

backend/app/semantic_page/
  graph.py
  builder.py
  classifiers.py
  target_builder.py
  serializers.py
  cache.py

backend/app/capabilities/
  registry.py
  browser_capabilities.py
  manifest.py

backend/app/policy/
  engine.py
  rules.py
  decisions.py

backend/app/mission/
  criteria.py
  fsm.py
  evidence.py
  projections.py

backend/app/world_model/
  model.py
  source_graph.py
  reasoning_memory.py
  projections.py

backend/app/grounding/
  targets.py
  resolver.py
  candidates.py
  ambiguity.py

backend/app/verification/
  validation_object.py
  goal_validator.py
  extraction_validator.py

backend/app/observability/
  metrics.py
  tracing.py
  health.py
```

Extension additions:

```text
extension/src/ledger/
  eventClient.ts
  projections.ts

extension/src/capabilities/
  manifest.ts

extension/src/observability/
  trace.ts

extension/src/types/v3.ts
```

Existing modules remain and are adapted incrementally.

## 3. Versioned Contracts

All durable V3 contracts include:

```text
schema_version: string
producer: string
created_at: ISO timestamp
run_id/session_id
```

Contract versions:

| Contract | Initial Version | Compatibility Rule |
|---|---|---|
| Run Ledger Event | `run_ledger.event.v1` | append-only; never mutate event semantics |
| Planner Packet | `planner_packet.v1` | additive fields only within V3.0-V3.2 |
| Semantic Page Graph | `semantic_page_graph.v1` | builder version in metadata |
| Mission State | `mission_state.v1` | state names stable for a minor version |
| Validation Object | `validation.v1` | `sgv_verified` derived for V2 compatibility |
| Source/World Model | `world_model.v1` | provenance required for promoted facts |
| Capability Registry | `capability_registry.v1` | capability ids stable, versions explicit |

Deprecation:

- Mark deprecated in schema.
- Continue emitting for two minor versions.
- Add migration test.
- Remove only after production validation confirms no consumer.

## 4. Feature Flags

Flags live in backend config and extension config where needed.

Flag states:

- `off`
- `shadow`
- `active`

Required flags:

```text
V3_RUN_LEDGER
V3_TRACE_PARITY
V3_CAPABILITY_REGISTRY
V3_SEMANTIC_GRAPH
V3_CONTEXT_PACKET
V3_SEMANTIC_TARGETS
V3_INTENT_GROUNDING
V3_MISSION_FSM
V3_VALIDATION_OBJECT
V3_POLICY_ENGINE
V3_VISUAL_OBSERVATION
V3_WORLD_MODEL
V3_SITE_MEMORY
```

Implementation rule:

- Every new subsystem must support `off` and `shadow` before `active`.
- `shadow` may write telemetry/ledger events but must not change user behavior.

## 5. Run Ledger Specification

### 5.1 Event Shape

```json
{
  "schema_version": "run_ledger.event.v1",
  "event_id": "uuid",
  "run_id": "session id",
  "step_index": 1,
  "event_type": "planner.response",
  "created_at": "iso timestamp",
  "producer": "backend.workflow_orchestrator",
  "payload": {},
  "links": {
    "parent_event_id": null,
    "observation_id": "uuid",
    "trace_id": "uuid"
  }
}
```

### 5.2 Event Types

```text
run.started
observation.captured
semantic_graph.built
planner.packet_built
planner.requested
planner.responded
planner.parsed
policy.evaluated
grounding.resolved
execution.started
execution.completed
verification.completed
mission.updated
workspace.updated
tab.updated
report.verified
goal_convergence.assessed
strategy_context.prepared
planner_recovery.prepared
user.input_requested
user.input_received
run.completed
run.failed
run.cancelled
```

### 5.3 Projections

Required projections:

- prior steps projection;
- mission snapshot projection;
- task workspace projection;
- tab workspace projection;
- planner trace projection;
- validation timeline projection;
- production failure report projection.

## 6. Semantic Page Graph Specification

### 6.1 Graph Schema

```json
{
  "schema_version": "semantic_page_graph.v1",
  "graph_id": "uuid",
  "observation_id": "uuid",
  "builder_version": "v1",
  "url": "",
  "title": "",
  "page_type": "search_results",
  "nodes": [],
  "edges": [],
  "facts": [],
  "targets": [],
  "metadata": {
    "source": "dom_a11y",
    "build_ms": 0,
    "input_hash": ""
  }
}
```

### 6.2 Node Types

```text
page
section
result_set
result_item
entity
fact
form
field
control
navigation
dialog
table
row
download
upload
error_state
visual_region
```

### 6.3 Target Shape

```json
{
  "target_id": "target.repo_home.rank_1",
  "target_type": "link",
  "semantic_role": "repository_home",
  "label": "lightpanda-io/browser",
  "entity_ref": "entity.repo.1",
  "locator_candidates": [],
  "confidence": 0.9
}
```

Planner consumes target ids. Grounding consumes locator candidates.

## 7. Capability Registry Specification

Capability contract:

```json
{
  "id": "browser.click",
  "version": "1.0.0",
  "purpose": "Activate a visible page control or link",
  "inputs_schema": {},
  "outputs_schema": {},
  "permissions": ["page_interaction"],
  "execution_environment": "extension.content_script",
  "constraints": ["non_destructive_only_without_confirmation"],
  "safety_class": "safe",
  "feature_flag": null
}
```

Registry consumers:

- planner packet builder;
- policy engine;
- grounding engine;
- execution router;
- tests;
- documentation.

## 8. Planner Packet Specification

Planner Packet:

```json
{
  "schema_version": "planner_packet.v1",
  "run": {},
  "mission_context": {},
  "task_context": {},
  "browser_context": {},
  "page_context": {},
  "memory_context": {},
  "policy_context": {},
  "capability_context": {},
  "recovery_context": {},
  "validation_context": {},
  "output_contract": "planner_contract_v2",
  "budget_metadata": {}
}
```

Rules:

- No raw DOM.
- No raw password values.
- No screenshots unless visual flag and policy allow.
- Include only bounded recent ledger entries.
- Include capability manifest, not hardcoded prose.
- Include semantic graph summary, not full graph by default.

## 9. Mission FSM Specification

State shape:

```json
{
  "schema_version": "mission_state.v1",
  "state": "collecting",
  "mode": "COLLECT",
  "goal": "",
  "current_subgoal": "",
  "completed_objectives": [],
  "remaining_objectives": [],
  "evidence_required": [],
  "evidence_collected": [],
  "blockers": [],
  "progress_estimate": 0.4,
  "confidence": "medium"
}
```

Allowed states:

```text
initialized
searching
collecting
extracting
verifying
comparing
report_ready
awaiting_user
recovering
blocked
completed
cancelled
failed
```

Mission FSM outputs advisory planner context until validation phase makes it authoritative for completion.

## 10. Validation Object Specification

```json
{
  "schema_version": "validation.v1",
  "status": "not_satisfied",
  "goal_ref": "goal.main",
  "claim_ref": "planner.report.1",
  "required_evidence": [],
  "observed_evidence": [],
  "missing_evidence": [],
  "contradictions": [],
  "uncertainty_reason": null,
  "confidence": 0.72,
  "source_refs": []
}
```

Statuses:

- `satisfied`
- `not_satisfied`
- `contradicted`
- `uncertain`

Compatibility:

- `sgv_verified = validation.status == "satisfied"`.

## 11. World Model Specification

World Model:

```json
{
  "schema_version": "world_model.v1",
  "entities": [],
  "relationships": [],
  "evidence": [],
  "hypotheses": [],
  "conflicts": [],
  "open_questions": []
}
```

Evidence must include:

- source URL;
- tab id if available;
- graph node id;
- extraction method;
- timestamp;
- confidence;
- privacy classification.

Reasoning Memory:

```json
{
  "hypotheses_considered": [],
  "rejected_strategies": [],
  "alternatives": [],
  "planner_confidence_history": [],
  "contradiction_history": []
}
```

## 12. Policy Engine Specification

Policy decision:

```json
{
  "schema_version": "policy_decision.v1",
  "decision": "allow",
  "risk_level": "safe",
  "requires_user_confirmation": false,
  "requires_handoff": false,
  "reasons": [],
  "constraints": []
}
```

Decision values:

- `allow`
- `allow_with_confirmation`
- `block`
- `handoff_required`

Policy evaluates:

- planner intent;
- grounded action;
- file transfer;
- tab close;
- auth credential fields;
- payment/purchase/delete/destructive actions;
- visual capture;
- data exfiltration risk.

## 13. Grounding Specification

Grounding input:

- planner outcome;
- semantic target id if present;
- semantic page graph;
- capability registry;
- policy constraints;
- legacy selector fallback.

Grounding output:

```json
{
  "schema_version": "grounding_result.v1",
  "status": "resolved",
  "target_id": "",
  "action": {},
  "locator_candidates": [],
  "selected_locator": "",
  "confidence": 0.91,
  "ambiguity": null
}
```

Statuses:

- `resolved`
- `ambiguous`
- `not_found`
- `policy_blocked`

## 14. Performance Budgets

| Component | Target | Warning | Failure | Measurement |
|---|---:|---:|---:|---|
| Semantic graph build | 80 ms | 200 ms | 500 ms | browser/backend timer |
| Context packet build | 50 ms | 150 ms | 300 ms | backend timer |
| Planner provider latency | 8 s | 20 s | 60 s | provider trace |
| Grounding resolution | 30 ms | 100 ms | 250 ms | backend/extension timer |
| Execution action | 1 s | 5 s | 15 s | extension telemetry |
| Verification | 50 ms | 150 ms | 300 ms | extension/backend timer |
| Ledger write | 20 ms | 75 ms | 200 ms | DB timer |
| Ledger replay | 100 ms | 300 ms | 1 s | projection timer |
| Planner packet tokens | 8k | 16k | 24k | tokenizer estimate |
| Trace size per run | 2 MB | 10 MB | 25 MB | artifact size |
| Extension memory | 75 MB | 150 MB | 250 MB | extension diagnostics |

Failure thresholds should log warnings first; hard failure only when continuing would risk data loss, runaway cost, or broken workflow.

## 15. Observability Specification

Metrics:

- Mission Success Rate
- Planner Outcome Distribution
- Grounding Accuracy
- Planner Latency
- Provider Error Rate
- Recovery Rate
- Validation Accuracy
- Token Usage
- Context Size
- Ledger Replay Time
- Semantic Graph Build Time
- Human Handoff Rate
- Policy Block Rate
- Visual Fallback Rate

Logs:

- structured JSON logs;
- run id and event id required;
- no raw secrets or password values;
- provider response logging must remain unicode-safe.

Distributed traces:

```text
run
  observe
  build_graph
  build_packet
  planner_call
  parse_response
  policy_check
  grounding
  execution
  verification
  ledger_write
```

Health indicators:

- backend healthy;
- DB healthy;
- provider healthy;
- extension connected;
- active tab accessible;
- ledger writable;
- trace sink healthy.

Dashboards:

- daily production validation score;
- failure taxonomy distribution;
- latency and token budget;
- policy/handoff rate;
- recovery effectiveness;
- graph/grounding accuracy.

Alerts:

- provider 4xx/5xx spike;
- ledger write failures;
- validation false-positive regression;
- planner no-action spike;
- context size above failure threshold;
- extension execution failure spike.

## 16. Migration Strategy

Phase rollout:

1. V3.0 Foundation
   - feature flags;
   - run ledger;
   - trace parity;
   - capability registry skeleton.

2. V3.1 Semantic Intelligence
   - semantic graph schema;
   - graph builder;
   - context packet shadow, then active.

3. V3.2 Intent Grounding
   - semantic targets;
   - grounding adapter;
   - legacy selector fallback.

4. V3.3 Mission Intelligence
   - mission criteria;
   - mission FSM;
   - mission packet projection.

5. V3.4 Validation
   - validation object;
   - criteria-based report/completion validation;
   - compatibility with `sgv_verified`.

6. V3.5 Policy And Vision
   - policy engine;
   - visual observation gated by policy;
   - visual target metadata.

7. V3.6 World Model And Learning
   - world model;
   - reasoning memory;
   - site memory.

## 17. Testing Strategy

Test layers:

- unit tests for each contract/model;
- projection tests for ledger;
- snapshot tests for semantic page graph;
- prompt packet tests;
- grounding resolver tests;
- policy decision tests;
- mission FSM transition tests;
- validation object tests;
- extension workflow tests;
- backend integration tests;
- production validation smoke tests;
- nightly benchmark for behavior-affecting changes.

Required smoke tasks:

1. deterministic invoice report;
2. GitHub repository comparison;
3. Google search extraction;
4. basic form fill;
5. multi-tab research;
6. auth handoff after policy phase;
7. visual/custom UI after visual phase.

## 18. ADRs Required Before Implementation

The following ADR files should be created before or during V3.0:

```text
docs/adrs/ADR-001-canonical-run-ledger.md
docs/adrs/ADR-002-preserve-planner-contract-v2.md
docs/adrs/ADR-003-deterministic-semantic-page-graph.md
docs/adrs/ADR-004-capability-registry.md
docs/adrs/ADR-005-mission-fsm.md
docs/adrs/ADR-006-validation-object-uncertainty.md
docs/adrs/ADR-007-world-model.md
docs/adrs/ADR-008-feature-flag-rollout.md
docs/adrs/ADR-009-policy-engine.md
docs/adrs/ADR-010-intent-grounding.md
```

## 19. Readiness Review

V3.0 is ready to implement when:

- feature flag states are defined;
- ledger event schema is approved;
- migration approach for existing `WorkflowEvent` is approved;
- trace privacy rules are approved;
- compatibility tests are identified;
- rollback path is clear.

V3.1 is ready when:

- page graph schema is approved;
- fixture page graph snapshots exist;
- graph builder budget is accepted.

V3.2 is ready when:

- semantic targets are stable;
- grounding ambiguity policy is approved;
- V2 fallback is tested.

V3.3 is ready when:

- mission criteria taxonomy is approved;
- FSM transitions are approved.

V3.4 is ready when:

- validation statuses and compatibility mapping are approved.

## 20. Final Implementation Rule

Every V3 component must satisfy this checklist before active rollout:

```text
Feature flag exists.
Schema version exists.
Unit tests pass.
Integration tests pass.
Telemetry exists.
Performance budget measured.
Privacy review passed.
Rollback path tested.
Production smoke validation passed.
```

No component should become planner-visible or routing-active before this checklist is complete.

## 21. Final Freeze Refinements

The following refinements are approved for the frozen V3 implementation specification. They extend the existing plan and do not change Planner Contract V2, the backward compatibility strategy, or the feature-flag migration approach.

### 21.1 Capability Platform Specification

The existing Capability Registry becomes the Capability Platform.

Responsibilities:

- register available capabilities
- discover runtime availability
- version capability contracts
- expose capability health
- expose permission requirements
- expose execution constraints
- record capability metrics

Initial repository structure:

```text
backend/app/capability_platform/__init__.py
backend/app/capability_platform/registry.py
backend/app/capability_platform/discovery.py
backend/app/capability_platform/health.py
backend/app/capability_platform/permissions.py
backend/app/capability_platform/constraints.py
backend/app/capability_platform/metrics.py
extension/src/capabilities/manifest.ts
extension/src/capabilities/health.ts
```

Core contract:

```text
CapabilityDescriptor
  id
  version
  provider
  purpose
  inputs_schema
  outputs_schema
  permissions
  constraints
  environments
  health
  metrics
  feature_flag

CapabilityHealth
  status: available | degraded | unavailable
  checked_at
  latency_ms
  error_rate
  reason
```

Planner integration:

- planner receives only a compact capability summary in the planner context packet;
- unavailable or unauthorized capabilities are not advertised as usable;
- capability metadata is advisory unless policy or execution explicitly enforces it.

Non-goals:

- no capability marketplace;
- no dynamic plugin installation;
- no new planner outcomes;
- no provider-specific planning logic.

### 21.2 Scheduler Specification

The Scheduler is introduced as a lightweight runtime boundary.

Responsibilities:

- one active foreground workflow per user task;
- delayed wait and resume;
- retry scheduling for existing bounded recovery policies;
- background jobs for trace export, replay, evaluation, cleanup, and scorecards;
- future parallel execution coordination.

Initial repository structure:

```text
backend/app/scheduler/__init__.py
backend/app/scheduler/queue.py
backend/app/scheduler/jobs.py
backend/app/scheduler/policies.py
extension/src/workflow/workflowScheduler.ts
```

Core contract:

```text
ScheduledWorkItem
  id
  run_id
  kind
  status: pending | running | delayed | completed | failed | cancelled
  dependency_ids
  earliest_start_at
  attempt
  max_attempts
  created_at
  updated_at
```

Boundary:

- Scheduler decides when eligible work runs;
- Workflow Orchestrator decides workflow semantics;
- Planner decides what outcome to produce.

Non-goals:

- no parallel browsing in V3.0;
- no planner-owned queue;
- no second workflow orchestrator.

### 21.3 Agent Cognitive Core Specification

The Agent Cognitive Core is a boundary over durable reasoning state.

Included components:

- Mission FSM
- World Model
- Reasoning Memory
- Goal Graph
- Evidence Tracking
- Hypothesis Management

Initial repository structure:

```text
backend/app/cognitive_core/__init__.py
backend/app/cognitive_core/facade.py
backend/app/cognitive_core/mission_fsm.py
backend/app/cognitive_core/world_model.py
backend/app/cognitive_core/reasoning_memory.py
backend/app/cognitive_core/goal_graph.py
backend/app/cognitive_core/evidence.py
backend/app/cognitive_core/hypotheses.py
```

Core contract:

```text
CognitiveSnapshot
  mission_state
  active_goal
  completed_objectives
  pending_objectives
  evidence_summary
  known_conflicts
  hypotheses
  reasoning_memory_summary
  confidence
```

Boundary:

- Cognitive Core maintains state;
- Context Packet Builder renders compact planner-facing context;
- Planner remains the only component that chooses browser actions.

Non-goals:

- no second planner;
- no hidden action generation;
- no unbounded memory dump into prompts.

### 21.4 Cost Controller Specification

Performance Budgets expand into a Cost Controller.

Responsibilities:

- token budget tracking;
- vision budget tracking;
- provider usage tracking;
- latency budget tracking;
- workflow duration tracking;
- cost-aware planner guidance;
- budget telemetry.

Initial repository structure:

```text
backend/app/cost_controller/__init__.py
backend/app/cost_controller/budgets.py
backend/app/cost_controller/meter.py
backend/app/cost_controller/policy.py
backend/app/cost_controller/telemetry.py
```

Core contracts:

```text
CostBudget
  run_id
  max_tokens
  max_vision_calls
  max_provider_cost
  max_latency_ms
  max_workflow_duration_ms

CostDecision
  status: within_budget | near_limit | exceeded
  reason
  planner_guidance
  hard_stop
```

Initial behavior:

- shadow or advisory mode;
- no hard stop unless an existing safety or product limit requires it;
- budget guidance may be included in planner context after the context packet exists.

Non-goals:

- no provider router replacement;
- no planner override;
- no billing system.

### 21.5 Evaluation Framework Specification

The Evaluation Framework is production-adjacent and outside the live request path.

Responsibilities:

- replay production runs;
- compare planner versions;
- score mission success;
- score grounding accuracy;
- score validation accuracy;
- score context compression quality;
- produce production scorecards;
- automate benchmark comparison.

Initial repository structure:

```text
backend/app/evaluation/__init__.py
backend/app/evaluation/replay.py
backend/app/evaluation/scoring.py
backend/app/evaluation/scorecards.py
backend/app/evaluation/comparisons.py
backend/app/evaluation/export.py
docs/production_validation/
```

Core contracts:

```text
EvaluationRun
  id
  source_run_id
  planner_version
  capability_manifest_version
  started_at
  completed_at
  status

EvaluationScorecard
  evaluation_run_id
  task_success
  planner_accuracy
  grounding_accuracy
  validation_accuracy
  execution_success
  mission_progress_accuracy
  regression_flags
```

Boundary:

- Evaluation reads ledger and trace artifacts;
- Evaluation never changes live workflow routing;
- Evaluation outputs evidence for engineering decisions.

Non-goals:

- no production hot-path dependency;
- no automatic prompt mutation;
- no automatic rollout decision.

## 22. Updated Repository Structure Addendum

The V3 repository structure should include these new top-level backend areas:

```text
backend/app/capability_platform/
backend/app/scheduler/
backend/app/cognitive_core/
backend/app/cost_controller/
backend/app/evaluation/
```

Extension additions should remain narrow:

```text
extension/src/capabilities/
extension/src/workflow/workflowScheduler.ts
```

These directories must remain empty or skeletal until the milestone that needs them. Do not populate future-phase modules ahead of use.

## 23. Updated Migration Roadmap

### V3.0 Foundation

Add:

- feature flags;
- contract versioning;
- Canonical Run Ledger;
- trace parity;
- Capability Platform skeleton;
- Cost Controller shadow mode;
- Scheduler shell.

Do not make new components planner-active until compatibility tests pass.

### V3.1 Semantic Intelligence

Add:

- Semantic Page Graph;
- Context Packet Builder;
- Cognitive Core boundary;
- compact planner context adapters.

### V3.2 Intent Grounding

Add:

- semantic targets;
- grounding confidence;
- grounding fallback;
- Capability Platform integration for executable affordances.

### V3.3 Mission Intelligence

Add:

- active Mission FSM;
- Goal Graph;
- Reasoning Memory;
- Evidence Tracking;
- CognitiveSnapshot generation.

### V3.4 Validation

Add:

- explicit Validation Object;
- evidence sufficiency;
- contradiction handling;
- compatibility mapping to existing `sgv_verified`.

### V3.5 Policy, Vision, and Scheduling

Add:

- Policy Engine;
- visual observation gate;
- Scheduler delayed work;
- bounded retry scheduling;
- Cost Controller advisory planner guidance.

### V3.6 Learning and Evaluation

Add:

- World Model projections;
- site memory;
- production replay;
- scorecards;
- planner version comparison.

## 24. Updated ADR List

The ADR set should include the previously required ADRs plus:

```text
docs/adrs/ADR-011-capability-platform.md
docs/adrs/ADR-012-scheduler-boundary.md
docs/adrs/ADR-013-agent-cognitive-core.md
docs/adrs/ADR-014-cost-controller.md
docs/adrs/ADR-015-evaluation-framework.md
```

ADR-004 should either be renamed from Capability Registry to Capability Platform or superseded by ADR-011. The preferred path is to keep ADR-004 as the original registry decision and add ADR-011 as the approved expansion.

## 25. Freeze Readiness

1. Is the architecture sufficiently complete to begin implementation?

Yes. The V3 blueprint, review, and implementation specification now define stable boundaries for workflow state, planning context, execution capabilities, costs, scheduling, validation, and evaluation.

2. Are major risks unresolved?

No major architectural blockers remain. The remaining risks are implementation risks: context growth, duplicate orchestration, premature enforcement, privacy controls, and backward compatibility. Each is addressed through feature flags, versioned contracts, shadow mode, and rollback requirements.

3. Would delaying implementation provide benefit?

No. Further architecture-only work is unlikely to produce stronger evidence than a feature-flagged V3.0 implementation with trace parity and replay support.

4. Can the architecture evolve to Comet/Operator-class capability without rewrite?

Yes. Capability Platform, Scheduler, Agent Cognitive Core, Cost Controller, and Evaluation Framework provide the extension points needed for additional browser, vision, memory, tool, and long-running workflow capabilities without replacing Planner Contract V2.

Final recommendation: freeze the V3 architecture and begin V3.0 implementation.
