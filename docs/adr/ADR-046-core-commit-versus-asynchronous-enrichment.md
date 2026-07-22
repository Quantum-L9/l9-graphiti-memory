# ADR-046: Core Commit versus Asynchronous Enrichment

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-046-core-commit-versus-asynchronous-enrichment.md
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

The legacy DAG placed reasoning, embeddings, insights, world-model updates, and checkpoints in the mandatory write sequence. Failures created complex fallback tiers.

## Decision

Core commit includes authorization, normalization, validation, admission, record/status/receipt persistence, and outbox creation. Graph projection, embeddings, atomic fact extraction, promotion analysis, and analytics are asynchronous consumers.

## Alternatives Considered

- Keep one giant ordered DAG
- Run enrichment before persistence
- Skip canonical write if projection is down

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Core record is durable before optional work
- Consumers are idempotent
- Optional failures never masquerade as committed effects

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Outbox integration tests
- Worker retry tests
- Core write with projection failure test

## Rollback Conditions

Stop all consumers while maintaining canonical writes; replay outbox after recovery.

## Supersedes / Superseded By

Replaces the original SubstrateDAG ownership model.

No later ADR supersedes this decision as of 2026-07-21.
