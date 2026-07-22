# ADR-013: Transport Abstraction and Vendor Neutrality

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-013-transport-abstraction-and-vendor-neutrality.md
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

The v0.2 repo migrated from a dead VPS to Zep Cloud but retained assumptions about tool names and silent backend fallback.

## Decision

Graph and semantic providers implement ProjectionAdapter. The core imports only ports. Backend choice is explicit: none, HTTP Graphiti MCP, or Zep. Production never silently switches providers when initialization fails. The HTTP adapter discovers provider tools and supports the current Graphiti add_memory, search_memory_facts, search_nodes, and delete_episode surface plus the older add_episode and search_facts compatibility names.

## Alternatives Considered

- Hard-code Zep Cloud into MemoryService
- Restore implicit localhost Graphiti fallback
- Expose raw provider clients to adapters

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Provider errors are typed and observable
- Provider configuration is distinct from verified connectivity; Zep remains unverified until a real operation succeeds
- Provider-specific fields stay outside canonical contracts
- A no-projection configuration remains fully functional

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Adapter import and provider-dialect negotiation tests
- Stable projection-locator and erasure tests
- Provider health-state tests covering unverified, healthy, and unhealthy states
- Explicit configuration failure tests
- Live tests separated from deterministic CI

## Rollback Conditions

Switch projection_backend to none or another configured adapter; canonical SQLite records and outbox remain intact.

## Supersedes / Superseded By

Supersedes transport-only architecture that treated the backend as the entire memory system.

No later ADR supersedes this decision as of 2026-07-21.
