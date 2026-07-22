# ADR-047: Schema Migration and Legacy Record Compatibility

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-047-schema-migration-and-legacy-record-compatibility.md
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

The rewrite must ingest v0.2 episodes and selected legacy L9 records without corrupting history or preserving unsafe behavior.

## Decision

Migration is export, validate, dry-run, import, reconcile, then cutover. Upcasters translate shape only. Authorization, admission, taxonomy, and temporal law are v2. Legacy raw payload is retained in migration metadata where safe. Every import is idempotent.

## Alternatives Considered

- Dual-write indefinitely
- In-place mutate the v0.2 store
- Treat all legacy records as trusted identity memory

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Migration never bypasses v2 policy
- Unsupported versions fail with actionable errors
- Source archive and checksums are retained

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Legacy fixture suite
- Dry-run/import count reconciliation
- Post-import search and temporal checks

## Rollback Conditions

Restore the pre-migration database copy and run v0.2 read-only; keep the v2 import report for diagnosis.

## Supersedes / Superseded By

Completes the compatibility path defined in ADR-023 and ADR-035.

No later ADR supersedes this decision as of 2026-07-21.
