# ADR-018: Outbox and Write Recovery

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-018-outbox-and-write-recovery.md
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

Older systems used direct database fallbacks or best-effort graph writes. Bypassing governance to maximize persistence weakens correctness.

## Decision

Core persistence and outbox event creation occur atomically. OutboxWorker projects records asynchronously with bounded retries, exponential backoff, and terminal dead status. Replays use the same event ID and record digest.

## Alternatives Considered

- Direct raw SQL fallback
- Synchronous graph write inside the transaction
- Drop projection work on failure

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- No projection effect exists without a canonical record
- Retry state is durable
- Terminal failures remain inspectable and replayable

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Outbox retry tests
- Atomic transaction tests
- Idempotent projection tests

## Rollback Conditions

Stop the worker, set projection to none, and retain pending events for later replay.

## Supersedes / Superseded By

Replaces direct DB Tier 3 fallback and best-effort graph sync.

No later ADR supersedes this decision as of 2026-07-21.
