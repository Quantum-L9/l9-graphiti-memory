# ADR-027: Semantic, Episodic, and Meta-Memory Ownership

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-027-semantic-episodic-and-meta-memory-ownership.md
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

The packs mixed events, facts, procedures, identity, and meta-rules in generic blobs.

## Decision

The taxonomy defines distinct ownership and lifecycle. Episodic records preserve events, semantic records preserve generalized facts, procedural records preserve approved heuristics, and meta records preserve governed memory policies. The repository owns their persistence, not the reasoning process that creates candidates.

## Alternatives Considered

- One universal fact type
- Separate repositories for every class
- Allow consumers to redefine class meaning

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Class meaning is contract-versioned
- Promotion is explicit
- Reasoning systems submit candidates rather than mutating memory

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Class-specific admission tests
- Promotion lifecycle tests
- Retrieval priority tests

## Rollback Conditions

Map unsupported classes to observation only in an export adapter, retaining original class metadata.

## Supersedes / Superseded By

Harvests memory-tier separation from Memory Packs and L9_Original_Repo.

No later ADR supersedes this decision as of 2026-07-21.
