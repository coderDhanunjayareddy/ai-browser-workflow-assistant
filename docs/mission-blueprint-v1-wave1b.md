# Mission Blueprint V1 Wave 1B

Wave 1B makes Mission Blueprint a durable passive artifact. It does not
decompose missions, generate nodes automatically, enqueue ledger intents,
evaluate readiness, or affect Runtime V1 execution.

## Storage

The durable schema is additive:

- `mission_blueprints`
- `mission_blueprint_revisions`
- `mission_blueprint_nodes`
- `mission_blueprint_dependencies`

The current application creates SQLAlchemy tables through
`Base.metadata.create_all()`. `app.mission.blueprint.migrations` documents the
equivalent additive DDL and rollback order for environments that adopt explicit
migration runners.

## Repository

`MissionBlueprintRepository` is the storage interface. Mission Intelligence must
depend on this abstraction rather than SQLAlchemy records.

`SqlAlchemyMissionBlueprintRepository` is the first implementation.

## Service

`MissionBlueprintPersistenceService` owns passive storage operations:

- create
- load
- save
- save revision
- get revision
- list revisions
- list nodes
- serialize
- deserialize

It contains no decomposition or execution logic.

## APIs

Read-only inspection endpoints:

- `GET /mission/{mission_id}/blueprint`
- `GET /mission/{mission_id}/blueprint/nodes`
- `GET /mission/{mission_id}/blueprint/revisions`
- `GET /mission/{mission_id}/blueprint/revision/{revision}`

No public mutation API exists in Wave 1B.

## Feature Flag

`MISSION_BLUEPRINT_V1`

- `off`: persistence and inspection are disabled.
- `shadow`: blueprints may be stored and inspected; no execution impact.
- `active`: same behavior as `shadow` in Wave 1B.

Execution remains reserved for later waves.

## Runtime Isolation

Wave 1B does not modify Mission Ledger, Planner Contract V2, Workflow
Orchestrator behavior, Intent Runtime, Mission Completion, Browser Runtime, or
the extension execution loop.

## Wave 2 Shadow Decomposition

Wave 2 extends Mission Intelligence with a passive Blueprint Builder. It can
create and persist revision-1 Blueprints from mission understanding in shadow
mode, but generated Blueprints are still stored artifacts only. They do not
expand into Mission Ledger intents or influence execution.
