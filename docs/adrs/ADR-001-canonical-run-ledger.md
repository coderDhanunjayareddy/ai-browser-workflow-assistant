# ADR-001: Canonical Run Ledger

## Status

Accepted.

## Decision

V3 uses an append-only Canonical Run Ledger as the durable source of truth for run events.

## Consequences

Existing workflow state remains valid. V3 projections may be built from ledger events, but production routing does not depend on them until explicitly activated.
