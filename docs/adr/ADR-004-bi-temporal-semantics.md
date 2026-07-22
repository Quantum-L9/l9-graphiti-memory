# ADR-004: Bi-Temporal Semantics

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-004-bi-temporal-semantics.md
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

The repository described itself as bi-temporal but previously stored only timestamps. Legacy L9 code implemented partial valid-time history without a clean transaction-time contract.

## Decision

Each record carries valid_from and valid_to for domain truth, plus recorded_at and superseded_at for system knowledge. Searches independently accept valid_at and recorded_before. When recorded_before is omitted, it defaults to current transaction time rather than valid_at.

## Alternatives Considered

- Use one created_at timestamp
- Treat supersession as physical update
- Use graph-provider timestamps as canonical

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Valid intervals are half-open [valid_from, valid_to)
- Transaction history is append-only
- Past-valid queries do not imply past-recorded queries

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Temporal boundary unit tests
- SQLite and in-memory conformance tests
- Supersession history tests

## Rollback Conditions

Disable temporal filters only through the legacy export adapter; never rewrite existing coordinates.

## Supersedes / Superseded By

Refines the temporal claims in the original Graphiti architecture docs.

No later ADR supersedes this decision as of 2026-07-21.
