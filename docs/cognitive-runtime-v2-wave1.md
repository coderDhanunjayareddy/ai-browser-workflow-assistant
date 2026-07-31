# Cognitive Runtime V2 Wave 1 Foundation

## Purpose

Cognitive Runtime V2 Wave 1 introduces the passive reasoning foundation that future waves will use to close the loop between Runtime V1 evidence and Mission Blueprint V1 progress.

Wave 1 is additive and shadow-only. It does not execute providers, create intents, invoke the planner, modify Mission Ledger behavior, change Browser Control, or affect Runtime V1 execution.

## Architecture

```text
Mission Blueprint V1
        |
        v
Runtime V1 / Mission Ledger / Providers
        |
        v
Evidence
        |
        v
Cognitive Runtime V2 Wave 1
        |
        +-- Evidence Collection
        +-- Passive Progress Snapshot
        +-- Checkpoints
        +-- Metrics
```

Wave 1 only stores and inspects cognitive state. Future waves may use the foundation to update Blueprint progress and trigger expansion, clarification, recovery, or replanning.

## Package

The implementation lives in:

```text
backend/app/cognitive_runtime/
```

Files:

- `models.py` - domain models and validation
- `repository.py` - persistence interface and SQLAlchemy implementation
- `service.py` - passive service operations
- `context.py` - read-only subsystem aggregate
- `evidence.py` - evidence merge, dedupe, freshness, provenance utilities
- `progress.py` - passive progress snapshot computation
- `controller.py` - passive controller facade
- `metrics.py` - metrics collection helpers
- `versioning.py` - runtime version and compatibility metadata

## Domain Models

### CognitiveMission

Mission-scoped reasoning object:

- `mission_id`
- `blueprint_id`
- `blueprint_revision`
- `runtime_version`
- `state`
- `created_at`
- `updated_at`
- `metadata`

### CognitiveState

Cognitive lifecycle state. It is intentionally separate from Mission Ledger execution states.

Supported values:

- `initialized`
- `understanding`
- `ready`
- `executing`
- `waiting_browser`
- `waiting_user`
- `waiting_external`
- `replanning`
- `recovering`
- `completed`
- `failed`
- `cancelled`

### CognitiveEvidence

Provider-independent normalized evidence:

- `evidence_id`
- `mission_id`
- `source`
- `provider`
- `evidence_type`
- `payload`
- `confidence`
- `timestamp`
- `provenance`

### EvidenceCollection

Mission evidence set with:

- merge
- deduplication
- provenance lookup
- serialization

### ProgressSnapshot

Diagnostic-only progress view:

- completed nodes
- ready nodes
- blocked nodes
- waiting nodes
- evidence coverage
- completion percentage

### CognitiveCheckpoint

Resumable passive reasoning checkpoint:

- checkpoint id
- mission id
- Blueprint revision
- serialized state
- timestamp

### RuntimeVersion

Semantic runtime version object with compatibility checks.

### CognitiveMetrics

Collected diagnostic metrics:

- reasoning iterations
- clarification count
- evidence count
- confidence average
- recovery count
- replanning count
- execution duration

## Database

Wave 1 adds four tables:

- `cognitive_missions`
- `cognitive_checkpoints`
- `cognitive_evidence`
- `cognitive_metrics`

No existing execution table is modified.

## Repository

`CognitiveRuntimeRepository` supports:

- `create`
- `update`
- `get`
- `delete`
- `save_checkpoint`
- `list_checkpoints`
- `save_metrics`
- `get_metrics`
- `save_evidence`
- `list_evidence`

`SqlAlchemyCognitiveRuntimeRepository` is the production implementation.

## Service

`CognitiveRuntimeService` supports:

- create runtime
- load runtime
- save checkpoint
- restore checkpoint
- attach evidence
- compute progress snapshot
- retrieve metrics

It never executes providers, creates ledger intents, calls the planner, or mutates Runtime V1 execution state.

## Feature Flag

Flag:

```text
COGNITIVE_RUNTIME_V2
```

Modes:

- `off` - APIs return disabled
- `shadow` - passive runtime is available
- `active` - identical to shadow in Wave 1

## APIs

Read-only endpoints:

```text
GET /mission/{mission_id}/cognitive
GET /mission/{mission_id}/cognitive/checkpoints
GET /mission/{mission_id}/cognitive/evidence
GET /mission/{mission_id}/cognitive/progress
GET /mission/{mission_id}/cognitive/metrics
```

There are no mutation APIs in Wave 1.

## Boundaries

Cognitive Runtime V2 Wave 1 must not:

- create Mission Ledger intents
- dispatch providers
- execute Browser Control
- modify planner behavior
- modify Mission Completion behavior
- modify Workflow Orchestrator behavior
- modify extension behavior
- change Runtime V1 execution

## Future Waves

Future waves can build on this foundation to:

- update Blueprint node satisfaction from evidence
- trigger dynamic Blueprint expansion
- manage clarification lifecycle
- coordinate external waiting
- request replanning when evidence contradicts the Blueprint
- classify recovery paths

Those behaviors are intentionally not activated in Wave 1.

