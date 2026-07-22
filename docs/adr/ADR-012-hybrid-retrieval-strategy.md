# ADR-012: Hybrid Retrieval Strategy

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-012-hybrid-retrieval-strategy.md
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

The packs proposed graph, semantic, lexical, and temporal retrieval. Coupling all stores into the critical path made older systems fragile.

## Decision

The canonical store performs authorized temporal retrieval. Optional projections add graph or semantic candidate signals. RetrievalPlanner fuses scores and emits complete, partial, or failed receipts. Projection failure cannot be confused with zero matches.

## Alternatives Considered

- Make Zep the sole source of truth
- Require PostgreSQL, Neo4j, Redis, and vector search together
- Treat every backend failure as an empty result

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Canonical store success is independently reported
- Projection requirements are configuration, not implicit fallback
- Result digests include failures and hit IDs

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Projection failure tests
- Store conformance tests
- Result receipt digest tests

## Rollback Conditions

Set projection_backend to none and replay pending outbox events after projection recovery.

## Supersedes / Superseded By

Replaces transport-specific read semantics.

No later ADR supersedes this decision as of 2026-07-21.
