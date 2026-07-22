# ADR-011: Hydration and Context Budgeting

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-011-hydration-and-context-budgeting.md
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

Agent memory is useful only when it can be delivered inside bounded context windows. Earlier packs proposed load-bearing facts, constraints, examples, and token budgets.

## Decision

Hydration converts a task, entities, topics, classes, namespaces, and token budget into an immutable HydrationResult. ContextBudgetAllocator uses explicit class priority and deterministic token estimates, retaining source record IDs and search receipt status.

## Alternatives Considered

- Return every matching memory
- Summarize all results with an LLM by default
- Split ranked results into arbitrary halves

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Budget exhaustion is visible
- Governing constraints and decisions outrank examples
- Hydration never expands caller namespace authority

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Budget boundary tests
- Deterministic ordering tests
- Partial search propagation tests

## Rollback Conditions

Fallback to raw SearchReceipt output if hydration assembly fails; do not fabricate a complete bundle.

## Supersedes / Superseded By

Harvests context budgeting concepts from L9-Ops-MCP and Cognitive Twin packs.

No later ADR supersedes this decision as of 2026-07-21.
