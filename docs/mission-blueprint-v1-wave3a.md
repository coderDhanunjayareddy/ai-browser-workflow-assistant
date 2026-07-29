# Mission Blueprint V1 Wave 3A

Wave 3A adds diagnostic node readiness evaluation.

It answers one question:

> Which Blueprint nodes are eligible to become executable?

It does not generate Mission Ledger intents, execute nodes, call the Planner,
evaluate mission completion, or inspect browser/runtime state.

## Inputs

The evaluator consumes:

- a stored `MissionBlueprint`
- abstract `BlueprintEvidence`

Evidence is provider-independent. Examples:

- `node_satisfied`
- `node_blocked`
- `clarification_obtained`
- prerequisite evidence declared by a Blueprint node

## Outputs

`BlueprintReadinessSnapshot` contains:

- ready nodes
- waiting nodes
- blocked nodes
- unreachable nodes
- parallel-ready nodes
- critical-path-ready nodes
- per-node dependency reasons
- missing evidence
- blocking reasons
- supporting evidence ids

## Persistence

Readiness snapshots are stored in:

- `mission_blueprint_readiness_snapshots`

Snapshots are diagnostic artifacts only.

## APIs

Read-only endpoints:

- `GET /mission/{mission_id}/blueprint/readiness`
- `GET /mission/{mission_id}/blueprint/readiness/snapshots`

## Runtime Isolation

Wave 3A does not modify Mission Ledger, Workflow Orchestrator, Planner Contract
V2, Intent Runtime, Mission Completion, Browser Runtime, or the extension.
