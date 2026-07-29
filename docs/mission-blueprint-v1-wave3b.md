# Mission Blueprint V1 Wave 3B

Wave 3B adds passive Blueprint expansion into Mission Ledger intents.

## Responsibility Boundary

Blueprint decides what executable work should now exist.

Mission Ledger owns the durable executable intent records.

Intent Runtime remains the only execution path.

The expansion engine never calls provider executors, never dispatches intents,
never evaluates mission completion, and never replans.

## Expansion Engine

`BlueprintExpansionEngine.expand_ready_nodes(...)`:

- loads the stored Blueprint
- reads a readiness snapshot
- expands only READY nodes
- compiles each expanded node into one or more `IntentDispatchDirective`s
- writes those directives to Mission Ledger with status `QUEUED`
- records expansion history
- skips nodes already expanded for the same Blueprint revision

## Ledger References

Mission Ledger intents now have nullable Blueprint references:

- `blueprint_id`
- `blueprint_node_id`
- `blueprint_revision`

These do not change lifecycle semantics.

## Expansion History

Expansion records are stored in:

- `mission_blueprint_expansions`

Inspection endpoint:

- `GET /mission/{mission_id}/blueprint/expansions`

## Execution Isolation

Wave 3B creates executable work but does not execute it. Runtime V1 remains the
only execution authority through Mission Ledger assignment and Intent Runtime.
