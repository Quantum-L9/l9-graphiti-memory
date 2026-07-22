# ADR-033: Legacy Monolith Harvest and Rejection Record

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-033-legacy-monolith-harvest-and-rejection-record.md
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

L9 Repo memory and L9_Original_Repo contained over one hundred memory modules with valuable algorithms and heavy coupling.

## Decision

Harvest contracts, deterministic algorithms, security invariants, schema migration, authorization patterns, and validation tools. Reject god services, mandatory multi-database stacks, world-model ownership, agent execution, Slack ingestion, and generated metadata noise.

## Alternatives Considered

- Copy the memory directory wholesale
- Ignore all legacy work
- Keep the monolith as a runtime dependency

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Every harvested concept maps to a v2 owner
- No core.* monolith imports
- Rejected components are recorded in HARVEST_MAP.md

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Dependency scan
- Harvest map review
- No unresolved legacy imports

## Rollback Conditions

Revisit a rejected component only through a new ADR with measured need and a bounded interface.

## Supersedes / Superseded By

Records the disposition of L9 Repo memory packs.

No later ADR supersedes this decision as of 2026-07-21.
