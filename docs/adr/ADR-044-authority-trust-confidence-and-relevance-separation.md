# ADR-044: Authority, Trust, Confidence, and Relevance Separation

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-044-authority-trust-confidence-and-relevance-separation.md
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

Memory packs and legacy code used trust ladders, role weights, confidence, and importance interchangeably.

## Decision

Authority controls permitted actions. Trust describes source reliability. Confidence describes evidence strength. Relevance describes query match. Importance describes durable operational value. Recency influences ranking. These are separate fields and policies.

## Alternatives Considered

- Collapse all signals into one score
- Let high-authority sources bypass evidence
- Use confidence as authorization

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- No score grants namespace access
- High authority does not guarantee factual truth
- Ranking factors remain inspectable

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Contract field tests
- Policy separation review
- Negative authorization/ranking tests

## Rollback Conditions

Map legacy composite scores into metadata and start canonical factors at neutral defaults.

## Supersedes / Superseded By

Formalizes a key harvest conclusion across all packs.

No later ADR supersedes this decision as of 2026-07-21.
