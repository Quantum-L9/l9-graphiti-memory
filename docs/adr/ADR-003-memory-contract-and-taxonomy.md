# ADR-003: Memory Contract and Taxonomy

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-003-memory-contract-and-taxonomy.md
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

Older packs used free-form kinds such as lesson, manifest, session_summary, fact, and note. This made retention, promotion, retrieval, and authorization inconsistent.

## Decision

All records use a versioned MemoryRecord contract and a controlled taxonomy: identity, preference, constraint, decision, episodic, semantic, procedural, observation, insight, and meta. Compatibility aliases are normalized at ingestion rather than stored as new categories.

## Alternatives Considered

- Preserve arbitrary string kinds
- Reduce all memory to facts and episodes
- Infer type only during retrieval

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Persistent records declare schema_version and memory_class
- Unknown classes fail validation
- Taxonomy changes require an ADR, upcaster, and regression fixture

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Pydantic contract tests
- Legacy kind upcast tests
- JSON schema/package resource validation

## Rollback Conditions

Rollback uses the legacy episode adapter to export v2 records as observation episodes while preserving original class in metadata.

## Supersedes / Superseded By

Replaces the unversioned kind field in EpisodeContract.

No later ADR supersedes this decision as of 2026-07-21.
