# ADR-041: LLM Extraction and Typed Failure Semantics

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-041-llm-extraction-and-typed-failure-semantics.md
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

Older LLM memory operations returned empty facts on exceptions, making failure indistinguishable from a valid empty extraction.

## Decision

Provider-backed extraction is optional and outside core commit. The EvidenceBoundProviderExtractor validates exact source ranges, while the deterministic extractor remains the default. Extractors return typed complete, partial, failed, or rejected results with model, prompt contract version, source digests, token budget, and evidence references. Empty success must be explicit and supported by evidence.

## Alternatives Considered

- Return empty objects on any exception
- Make LLM extraction mandatory for every write
- Trust free-form text parsing without schema validation

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Extraction failure never becomes no-result success
- Candidates pass normal admission
- Model output cannot assert caller identity

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Malformed output tests
- Timeout tests
- Evidence completeness tests

## Rollback Conditions

Disable the extractor and retain source records; no canonical write is rolled back.

## Supersedes / Superseded By

Corrects LLMMemoryOps silent-empty behavior.

No later ADR supersedes this decision as of 2026-07-21.
