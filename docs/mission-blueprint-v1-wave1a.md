# Mission Blueprint V1 Wave 1A

Wave 1A introduces only in-memory Mission Blueprint domain models. It does not
persist blueprints, generate intents, alter Planner Contract V2, or connect to
Runtime V1 execution.

## Feature Flag

`MISSION_BLUEPRINT_V1` controls explicit Blueprint creation and serialization.

- `off`: public creation and serialization APIs raise `BlueprintValidationError`.
- `shadow`: in-memory Blueprint APIs are available for diagnostics and tests.
- `active`: in-memory Blueprint APIs are available; no runtime behavior changes
  exist in Wave 1A.

The default is `off`.

## Public Interfaces

- `create_blueprint(...)`
- `validate_blueprint(blueprint)`
- `serialize_blueprint(blueprint)`
- `deserialize_blueprint(payload)`

These interfaces live in `app.mission.blueprint`.

## Domain Classes

- `MissionBlueprint`: declarative mission graph root.
- `BlueprintNode`: one mission-level objective or work node.
- `BlueprintDependency`: dependency edge between nodes.
- `BlueprintEvidenceRequirement`: evidence required to satisfy a node.
- `BlueprintExpansionRule`: declarative capability and intent-template hint for
  later waves.
- `ClarificationRequirement`: user clarification needed by one or more nodes.

## Validation Rules

Validation enforces:

- supported schema version
- required mission and blueprint identifiers
- non-empty objective
- at least one node
- unique node ids
- dependency references to known nodes
- no self-dependencies
- acyclic dependency graph
- node priority from 1 to 5
- evidence cardinality greater than zero
- confidence thresholds from 0 to 1
- expansion rules with capability and intent template
- Blueprint node states remain separate from Runtime Ledger execution states

## Runtime V1 Isolation

Wave 1A has no imports from Workflow Orchestrator, Mission Ledger, Intent
Runtime, Browser Control, Semantic Execution Kernel, or Mission Completion.
No runtime code calls Blueprint APIs. The new package is therefore inert unless
explicitly imported by tests or future Mission Intelligence code.
