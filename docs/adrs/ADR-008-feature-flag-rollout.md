# ADR-008: Feature Flag Rollout

## Status

Accepted.

## Decision

Every V3 subsystem starts behind feature flags with `off`, `shadow`, and `active` states.

## Consequences

Shadow mode may write diagnostics or ledger records, but it must not alter planner, workflow, or execution behavior.
