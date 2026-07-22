# ADR-040: Importance, Ranking, and Decay Policy

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-040-importance-ranking-and-decay-policy.md
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

Legacy code conflated source authority, role, confidence, importance, relevance, access, and recency. System messages were automatically treated as more important.

## Decision

RankingPolicy keeps lexical relevance, class priority, confidence, recency, access/importance metadata, and projection score as separate explainable factors. Policy version and factors are returned with each SearchHit. Authority is never a relevance multiplier.

## Alternatives Considered

- One opaque score from an embedding model
- Role-weighted importance
- Access count alone determines retention

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Every score is decomposable
- Weights are versioned
- Decay never changes source evidence

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Ranking factor tests
- Stable ordering fixtures
- Policy version receipt test

## Rollback Conditions

Select the prior policy version through configuration and re-run retrieval; records require no migration.

## Supersedes / Superseded By

Harvests ImportanceRecipe while rejecting authority conflation.

No later ADR supersedes this decision as of 2026-07-21.
