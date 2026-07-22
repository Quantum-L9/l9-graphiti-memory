# ADR-025: Storage Source of Truth and Backend Partitioning

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-025-storage-source-of-truth-and-backend-partitioning.md
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

Legacy systems distributed truth across PostgreSQL, Neo4j, pgvector, Zep, local JSON, and memory-bank files.

## Decision

RecordStore is the canonical source of truth for records, status events, receipts, locks, and outbox. Graph and semantic systems are rebuildable projections. SQLite is the default standalone store; future stores implement the same port.

## Alternatives Considered

- Make the graph database canonical
- Use each backend as co-equal truth
- Store only in provider SaaS

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Projection data can be deleted and rebuilt
- Canonical writes are atomic
- Store adapters preserve contract semantics

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Store conformance suite
- Projection rebuild test
- Backup and restore drill

## Rollback Conditions

Switch RecordStore adapter after export/import and conformance validation; projections are regenerated.

## Supersedes / Superseded By

Replaces multi-store ambiguous ownership.

No later ADR supersedes this decision as of 2026-07-21.
