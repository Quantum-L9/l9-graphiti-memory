# ADR-019: Observability and Evidence Receipts

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-019-observability-and-evidence-receipts.md
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

Pass-only reports and generic logs made it impossible to distinguish validation, degradation, and actual effects.

## Decision

Every material operation returns or stores a typed receipt with status, identifiers, policy versions, authorization, digests, warnings, failures, and timestamps. Structured logs supplement receipts but are not the audit source of truth.

## Alternatives Considered

- Use logs as the only evidence
- Emit one legacy universal envelope for every internal call
- Store only success receipts

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Rejected and duplicate writes also emit receipts
- Receipts are immutable
- Health reports expose canonical and optional dependency state

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Receipt schema tests
- SQLite receipt persistence test
- Failure receipt snapshots

## Rollback Conditions

Export receipts as JSONL before database rollback; replaying operations does not overwrite prior receipts.

## Supersedes / Superseded By

Replaces opaque prints and pass-only validation artifacts.

No later ADR supersedes this decision as of 2026-07-21.
