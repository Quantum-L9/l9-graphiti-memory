# ADR-035: Schema Registry and Upcasting

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-035-schema-registry-and-upcasting.md
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

Persistent memory outlives code versions. The original L9 schema registry had useful chained upcasters but was not consistently wired into reads.

## Decision

SchemaRegistry detects version, computes an explicit migration path, applies pure upcasters, and validates the resulting current MemoryRecord. SQLite reads and import paths use it. Missing paths fail loudly.

## Alternatives Considered

- One destructive database migration only
- Best-effort field guessing at every call site
- Keep every schema model active forever

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Upcasters do not mutate input
- Migration path is deterministic
- Every supported legacy version has tests

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Legacy episode upcast test
- Migration path error test
- Round-trip fixture test

## Rollback Conditions

Retain raw legacy export and restore the prior registry version; never partially rewrite records in place.

## Supersedes / Superseded By

Harvests and completes the schema registry from L9_Original_Repo.

No later ADR supersedes this decision as of 2026-07-21.
