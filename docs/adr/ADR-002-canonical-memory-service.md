# ADR-002: Canonical Memory Service

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-002-canonical-memory-service.md
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

The v0.2 CLI validated episodes while the MCP server wrote directly through transports. The original L9 monolith accumulated multiple ingestion services, DAGs, routes, and fallbacks.

## Decision

MemoryService is the only authorized production path for write, search, hydrate, get, conflict check, phase lock, promotion, pruning, and health. CLI, MCP, hooks, importers, and workers adapt requests into typed contracts and call MemoryService.

## Alternatives Considered

- Allow each adapter to optimize its own path
- Use the graph provider as the service boundary
- Keep separate read and write facades without shared authorization

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Every durable mutation emits a typed receipt
- Every adapter shares the same admission and authorization rules
- The storage adapter cannot be called by public adapters directly

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- AST scan for commit_write callers
- Integration tests across CLI/MCP/service
- Negative tests for unauthorized writes

## Rollback Conditions

Re-enable the legacy EpisodeContract adapter behind a feature flag; do not restore direct transport writes.

## Supersedes / Superseded By

Supersedes all duplicated write entrypoints in v0.2 and L9_Original_Repo.

No later ADR supersedes this decision as of 2026-07-21.
