# Cognitive Runtime V2 Wave 2: Evidence Interpretation Engine

## Purpose

Wave 2 extends Cognitive Runtime V2 with passive evidence interpretation.

It answers:

- what evidence exists
- how trustworthy evidence is
- whether evidence satisfies Blueprint requirements
- whether evidence is stale
- whether evidence contradicts other evidence
- what evidence is missing

It remains shadow-only. It does not execute providers, create Mission Ledger intents, modify Mission Blueprint, call the planner, alter Runtime V1, or evaluate mission completion.

## Components

### EvidenceInterpreter

`backend/app/cognitive_runtime/interpreter.py`

Coordinates passive evidence reasoning:

- normalizes evidence
- classifies evidence
- fuses evidence
- matches evidence to Blueprint requirements
- detects contradictions
- produces diagnostics

### EvidenceFusionEngine

`backend/app/cognitive_runtime/fusion.py`

Supports:

- provider-independent evidence merging
- duplicate collapse
- provenance preservation
- provider distribution
- confidence aggregation hooks

### ConfidenceEvaluator

`backend/app/cognitive_runtime/confidence.py`

Computes normalized confidence from:

- provider confidence
- freshness
- corroboration
- provenance quality

The score is diagnostic only.

### FreshnessEvaluator

`backend/app/cognitive_runtime/freshness.py`

Evaluates:

- evidence age
- expiration
- freshness score
- stale evidence flag

### ContradictionDetector

`backend/app/cognitive_runtime/contradiction.py`

Detects:

- conflicting field values
- incompatible claims from different evidence items
- duplicate-but-different observations

It reports contradictions but does not resolve them.

### EvidenceRequirementMatcher

`backend/app/cognitive_runtime/requirements.py`

Matches a Blueprint node's evidence requirements against an EvidenceCollection.

Outputs:

- satisfied requirements
- missing requirements
- partially satisfied requirements

It does not decide readiness, expansion, or completion.

### EvidenceDiagnostics

`backend/app/cognitive_runtime/diagnostics.py`

Reports:

- coverage
- missing evidence
- confidence
- freshness
- contradictions
- provider distribution
- provenance graph

## APIs

Read-only endpoints:

```text
GET /mission/{mission_id}/cognitive/evidence/diagnostics
GET /mission/{mission_id}/cognitive/evidence/coverage
GET /mission/{mission_id}/cognitive/evidence/confidence
GET /mission/{mission_id}/cognitive/evidence/contradictions
```

All endpoints are gated by:

```text
COGNITIVE_RUNTIME_V2
```

Flag behavior:

- `off`: disabled
- `shadow`: compute diagnostics only
- `active`: identical to shadow in Wave 2

## Database

Wave 2 adds no new tables.

It reuses Wave 1 Cognitive Runtime evidence persistence.

## Boundaries

Wave 2 must not:

- execute providers
- create intents
- modify Blueprint
- modify Mission Ledger
- modify Planner
- modify Browser Runtime
- modify Mission Completion
- modify Workflow Orchestrator
- modify Extension

## Future Integration

Future waves may use these diagnostics to inform:

- Blueprint node satisfaction
- dynamic expansion
- clarification lifecycle
- external waiting
- recovery classification
- replanning triggers

Those behaviors are intentionally not activated in Wave 2.

