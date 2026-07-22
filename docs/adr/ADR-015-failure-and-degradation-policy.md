# ADR-015: Failure and Degradation Policy

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-015-failure-and-degradation-policy.md
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

Legacy code swallowed search, prefetch, graph, and extraction failures. Other paths failed hard even when only telemetry was unavailable.

## Decision

Critical authorization, admission, canonical persistence, and audit receipt operations fail loudly. Optional projections and enrichment may degrade to partial with typed failure details. No critical failure is represented as an empty success.

## Alternatives Considered

- Fail open everywhere to preserve developer velocity
- Fail closed for all optional features
- Log exceptions and return empty structures

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Critical versus optional dependency is explicit
- Every degraded operation records the failed component
- Exception chains preserve root cause

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Fault-injection tests
- Partial/failed receipt tests
- Health report assertions

## Rollback Conditions

Disable optional adapters, not critical validation. If canonical store is unavailable, queue through the durable outbox import path rather than bypassing policy.

## Supersedes / Superseded By

Refines ADR-0055 from L9_Original_Repo for a standalone memory subsystem.

No later ADR supersedes this decision as of 2026-07-21.
