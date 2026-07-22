# ADR-031: Reasoning Lineage versus Private Reasoning

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-031-reasoning-lineage-versus-private-reasoning.md
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

Legacy modules stored and replayed reasoning traces. Persisting hidden chain-of-thought creates privacy, security, and product risks.

## Decision

The system stores decisions, evidence, concise rationales, source references, and transformation lineage. It does not require or expose private model chain-of-thought. Procedural synthesis consumes approved summaries or trace artifacts supplied by the owning runtime.

## Alternatives Considered

- Store raw hidden reasoning by default
- Store no rationale or evidence
- Let each consumer decide without contract

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Evidence lineage is sufficient for audit
- Private reasoning is not a required field
- User-visible rationale is explicit content, not hidden state

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Contract field audit
- No chain_of_thought field scan
- Procedural synthesis fixture review

## Rollback Conditions

Remove private reasoning fields during import and preserve only a digest plus operator-approved summary.

## Supersedes / Superseded By

Rejects raw reasoning-trace ownership from the legacy monolith.

No later ADR supersedes this decision as of 2026-07-21.
