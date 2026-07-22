# ADR-042: Offline Source Ingestion

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-042-offline-source-ingestion.md
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

The original repo built a transcript distiller for ADRs, READMEs, reports, and chats. It used machine-specific paths and lacked a standalone evidence contract.

## Decision

RepositoryBootstrapper and document import discover approved files, capture exact paths and digests, create evidence-bearing candidates, support dry-run, and write through MemoryService. Large-scale transcript import belongs in an optional tool using the same contracts.

## Alternatives Considered

- Read arbitrary home-directory files automatically
- Bypass admission for trusted docs
- Store one giant repository summary

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Input roots are explicit
- Every candidate has source path and digest
- Import is idempotent

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Bootstrap dry-run test
- Repeated import test
- Excluded private-path test

## Rollback Conditions

Keep the generated manifest and replay after correcting mappings; no partial direct store edits.

## Supersedes / Superseded By

Harvests the offline distiller concept.

No later ADR supersedes this decision as of 2026-07-21.
