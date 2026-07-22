# ADR-012: Scheduler Boundary

## Status

Accepted.

## Decision

V3 introduces a Scheduler boundary for queueing, delayed work, and retry scheduling.

## Consequences

The scheduler remains inactive in V3.0 and does not replace the production workflow loop.
