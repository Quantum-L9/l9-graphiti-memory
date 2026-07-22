# ADR-061: Local Receipt Guard Boundary

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-061-local-receipt-guard-boundary.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-22
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.2+

## Status

Accepted

## Context

Legacy editor hooks called a local component a Gate and stored hydration markers beside phase-lock data. This terminology implied that the package duplicated constellation Gate or owned workflow state.

## Decision

Rename the implementation concept to a local memory receipt guard. The guard performs no routing, admission, or network calls. It reads only a bounded, expiring verification cache containing hydration and phase-lock receipts. The historical module and hook filenames remain thin compatibility shims.

## Alternatives Considered

- Preserve the local component as a second Gate
- Remove mutation guards entirely
- Put editor workflow state into constellation Gate

## Rejected Alternatives

The alternatives duplicate Gate, weaken safety, or assign workflow ownership to the wrong layer.

## Invariants

- The guard owns no workflow graph or routing state
- Evidence is typed, expiring, and task-bound
- The compatibility module contains no persistence logic
- Invalid evidence fails closed only when enforcement is enabled

## Consequences

Positive: terminology and authority align while compatibility survives. Negative: legacy filenames remain until consumers migrate.

## Security Impact

Typed evidence parsing rejects malformed or stale state, and local mutation decisions cannot widen namespace or routing authority.

## Migration Impact

Consumers may continue calling the existing hook filenames. New integrations use `memory_guard` terminology.

## Validation Requirements

- Behavior tests for fresh, stale, missing, and phase-lock evidence
- Static check that the compatibility shim owns no state persistence
- Shell syntax validation

## Rollback Conditions

Disable the optional guard. Do not restore a stateful local Gate implementation.

## Supersedes / Superseded By

Supersedes the Gate terminology in ADR-017. No later ADR supersedes this decision.
