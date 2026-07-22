# ADR-005: Provenance and Evidence

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-005-provenance-and-evidence.md
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

Synthetic memory packs produced insights without source segments and reported confidence despite missing evidence. Existing episode writes often carried only a source description.

## Decision

Every record carries Provenance, EvidenceRef entries when applicable, source digests, extraction method, and confidence metadata. Inferred and aggregated memories are rejected unless evidence types match the confidence method.

## Alternatives Considered

- Trust model-generated confidence alone
- Store source text only in opaque metadata
- Permit evidence-free inferred memories at lower rank

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Confidence never substitutes for evidence
- Original source digest is preserved before redaction
- Transformation lineage is inspectable

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Contract validators for evidence methods
- Ingestion tests with missing evidence
- Digest stability tests

## Rollback Conditions

Quarantine evidence-incomplete candidates and retain their receipts; do not silently admit or discard them.

## Supersedes / Superseded By

Supersedes source_description-only provenance.

No later ADR supersedes this decision as of 2026-07-21.
