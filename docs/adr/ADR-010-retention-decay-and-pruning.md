# ADR-010: Retention, Decay, and Pruning

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-010-retention-decay-and-pruning.md
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

Legacy pruning mixed physical deletion, graph cleanup, and heuristic decay. Durable history and references could be lost.

## Decision

Retention affects active state and retrieval ranking. Expired records are archived through status events. Physical deletion is a separately authorized privacy operation, not routine pruning. Reference-aware rules block destructive removal while records are depended upon.

## Alternatives Considered

- Delete low-score records automatically
- Never expire any memory
- Let each backend apply independent TTL behavior

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Historical receipts remain durable
- Decay changes ranking, not source truth
- Pruning is dry-run by default

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Dry-run/apply tests
- Reference-safety tests
- Archived retrieval flag tests

## Rollback Conditions

Reactivate archived records by appending a status event; never reconstruct deleted history from projections.

## Supersedes / Superseded By

Replaces graph prune scripts as the primary retention mechanism.

No later ADR supersedes this decision as of 2026-07-21.
