# ADR-054: Strategy-Specific Hybrid Retrieval Receipts

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-054-strategy-specific-hybrid-retrieval-receipts.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-22
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.1+

## Status

Accepted

## Context

A projection advertising both graph and semantic retrieval can falsely report both strategies succeeded after one combined provider call. That produces decorative telemetry rather than execution evidence.

## Decision

Projection adapters expose strategy-specific search. RetrievalPlanner independently executes each supported requested strategy, labels each store attempt as provider:strategy, fuses record scores, and records separate success or failure evidence. Unsupported strategies are omitted rather than claimed.

## Alternatives Considered

- Call one generic projection search and mark every capability successful
- Always attempt every strategy
- Convert strategy errors into empty results

## Rejected Alternatives

- One call cannot prove multiple paths
- Unnecessary strategies waste latency and provider quota
- Empty results conceal degradation

## Invariants

- Every succeeded strategy corresponds to an executed call
- Strategy failures are distinct from zero matches
- The deterministic classifier selects bounded strategies
- Canonical retrieval remains available when optional projection strategies fail

## Consequences

Positive: Hybrid receipts become truthful and diagnosable

Negative: Multiple projection strategies can increase external calls

## Security Impact

Strategy-specific calls keep failure and data boundaries explicit. Authorization is resolved before provider access.

## Migration Impact

Adapters without strategy support may use one declared capability through the compatibility search method; they cannot claim multiple independent strategies.

## Validation Requirements

- Independent graph and semantic call tests
- Partial-receipt tests
- No-projection strategy omission tests

## Rollback Conditions

Disable optional projection strategies and use canonical lexical and temporal retrieval.

## Supersedes / Superseded By

Strengthens ADR-012 and ADR-039.

No later ADR supersedes this decision as of 2026-07-22.
