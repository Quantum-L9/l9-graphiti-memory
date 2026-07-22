# ADR-032: Performance SLOs and Partial Result Policy

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-032-performance-slos-and-partial-result-policy.md
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

Legacy specs included latency targets but often hid failures behind empty results. Memory operations need measurable behavior without pretending optional adapters are always healthy.

## Decision

Core writes target bounded local transaction latency measured by the executable local benchmark; search and hydrate expose measured status and component failures. Provider calls use configured timeouts and circuit breakers. Partial results are allowed only when the canonical store succeeds and optional components fail.

## Alternatives Considered

- Promise fixed latency without measurement
- Fail all searches when any projection fails
- Return partial data as complete

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Status reflects actual component outcomes
- Timeouts are explicit configuration
- SLO changes require benchmark evidence

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Fault-injection timing tests
- Receipt status assertions
- Benchmark script in release validation

## Rollback Conditions

Disable slow optional projections and operate from canonical retrieval while investigating.

## Supersedes / Superseded By

Harvests operational requirements from memory_spec_v3.0.

No later ADR supersedes this decision as of 2026-07-21.
