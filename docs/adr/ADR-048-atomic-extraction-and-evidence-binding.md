# ADR-048: Atomic Extraction and Evidence Binding

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-048-atomic-extraction-and-evidence-binding.md
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

Narrative episodes are useful source evidence but are poor independently retrievable facts. Earlier packs promised atomic extraction while leaving source ranges, rejection behavior, and provider-output grounding incomplete.

## Decision

Every distillation run produces atomic candidates with an exact source digest and source range. Deterministic extraction is the default. Provider-backed extraction is accepted only when every candidate is contained in its declared source lines. Rejected candidates remain visible in a typed distillation receipt.

## Alternatives Considered

- Store only the full narrative episode
- Trust provider-generated facts without source ranges
- Write extracted facts directly to a backend

## Rejected Alternatives

- Narrative-only storage weakens retrieval and conflict evaluation
- Ungrounded provider output cannot support confidence claims
- Direct writes bypass authorization, admission, and receipts

## Invariants

- Every extracted candidate has a source digest and range
- Provider candidates outside the declared excerpt are rejected
- Every admitted candidate enters through MemoryService
- An empty or failed extraction is distinguishable from zero valid facts

## Consequences

Positive: Atomic memory improves retrieval and conflict analysis

Negative: Extraction creates more records and requires idempotent source keys

## Security Impact

Source-bound evidence reduces fabricated-memory risk. Extraction does not grant authority to change identity or preferences.

## Migration Impact

Legacy narrative episodes remain valid source records. Atomic candidates are additive and reference their source evidence.

## Validation Requirements

- Deterministic extractor tests
- Provider grounding rejection tests
- Distillation receipt and idempotency tests

## Rollback Conditions

Disable distillation consumers and retain original source records; do not delete admitted atomic records without normal lifecycle controls.

## Supersedes / Superseded By

Implements the deferred portions of ADR-041 and ADR-042.

No later ADR supersedes this decision as of 2026-07-22.
