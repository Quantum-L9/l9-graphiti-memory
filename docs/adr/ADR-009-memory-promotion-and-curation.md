# ADR-009: Memory Promotion and Curation

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-009-memory-promotion-and-curation.md
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

The packs distinguished episodic, semantic, procedural, and meta-memory and proposed promotion based on repeated evidence. Automatic self-modification would be unsafe.

## Decision

PromotionPolicy is default-deny. Explicit confirmation, governance approval, test-backed repeated success, or other versioned evidence may create a promoted record. Promotion emits a new record and receipt; it never mutates the source record in place.

## Alternatives Considered

- Automatic promotion based on access count
- One static memory class forever
- Allow LLM confidence alone to promote procedures

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Procedural and meta promotion require stronger evidence
- Promotion lineage points to supporting records
- Promotion policy version is stored

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Promotion deny/allow tests
- Lineage assertions
- Authorization tests for promote action

## Rollback Conditions

Archive the promoted record and reactivate the source through a new status event; retain both histories.

## Supersedes / Superseded By

Harvests deterministic promotion rules from L9 Repo memory and Memory Packs.

No later ADR supersedes this decision as of 2026-07-21.
