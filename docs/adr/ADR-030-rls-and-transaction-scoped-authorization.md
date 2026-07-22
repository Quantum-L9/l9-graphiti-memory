# ADR-030: RLS and Transaction-Scoped Authorization

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-030-rls-and-transaction-scoped-authorization.md
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

The original L9 repository used transaction-local tenant variables for PostgreSQL row-level security. The standalone v2 defaults to SQLite but must preserve the same security semantics.

## Decision

Authorization is enforced in MemoryService and again at the storage boundary through tenant and namespace predicates. Future relational adapters should establish transaction-scoped RLS claims. Storage APIs always require tenant_id and never expose unrestricted list-all operations to public adapters.

## Alternatives Considered

- Application filtering only
- Database RLS only
- Global administrator connection for all reads

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Every query predicates tenant and namespace
- Administrative operations are explicit
- Storage conformance includes isolation

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Cross-tenant store tests
- SQL inspection for predicates
- Future PostgreSQL RLS integration test

## Rollback Conditions

Disable a nonconforming adapter and fall back to SQLite or in-memory test mode; do not weaken service authorization.

## Supersedes / Superseded By

Harvests governance context and RLS patterns from L9_Original_Repo.

No later ADR supersedes this decision as of 2026-07-21.
