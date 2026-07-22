# ADR-039: Retrieval Planning and Tier Fusion

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-039-retrieval-planning-and-tier-fusion.md
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

Later L9 code introduced a PipelineRouter for episodic, semantic, and procedural tiers with query rewriting. It still defaulted caller identity and hid some failures.

## Decision

Retrieval planning is deterministic first: authorized temporal canonical search, optional projection scores, class-aware ranking, and bounded hydration. Graph and semantic projection strategies execute independently and emit per-strategy receipts. Query rewriting and neural reranking remain optional future adapters that must provide the same evidence.

## Alternatives Considered

- Mandatory LLM query rewriting
- One global vector search
- Parallel tier services with independent authorization

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Authorization occurs before all retrieval
- Optional enrichers cannot widen result sets beyond canonical records without verification
- Each tier failure is reported

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Tier filter tests
- Projection fusion tests
- Future rewriter fault tests

## Rollback Conditions

Disable optional rewrite/rerank adapters and use canonical lexical-temporal ranking.

## Supersedes / Superseded By

Harvests PipelineRouter shape without its identity and failure defects.

No later ADR supersedes this decision as of 2026-07-21.
