# ADR-029: Temporal Coordinate Model

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-029-temporal-coordinate-model.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-21
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2+

## Status

Accepted

## Context

Temporal fields appeared under several names across packs: timestamp, reference_time, valid_at, created_at, invalid_at, source time, and transaction time.

## Decision

TemporalCoordinates is canonical: valid_from, valid_to, recorded_at, source_observed_at, superseded_at. All values are timezone-aware UTC. valid_to is exclusive. recorded_at is assigned by the service clock, never trusted from unprivileged callers.

## Alternatives Considered

- Store arbitrary timestamp maps
- Use naive datetimes
- Let providers define interval semantics

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- All persisted datetimes are timezone-aware
- Service owns transaction time
- Interval validation rejects inverted ranges

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Timezone validation tests
- Boundary query tests
- Legacy timestamp upcasters

## Rollback Conditions

Convert legacy timestamps through explicit upcasters and retain raw values in migration metadata.

## Supersedes / Superseded By

Expands ADR-004 with field-level law.

No later ADR supersedes this decision as of 2026-07-21.
