# ADR-007: Admission and Quarantine

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-007-admission-and-quarantine.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-04
/L9_META -->


**Date:** 2026-07-21
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2+

## Status

Accepted

## Context

Previous systems either wrote everything or rejected it in ad hoc code. Packs proposed relevance, trust, consent, deduplication, and quarantine but did not provide one deterministic contract.

## Decision

AdmissionEngine applies versioned policy after authorization and normalization. It returns admitted, rejected, duplicate, quarantined, or superseded decisions. Safety signals are review signals, not content rewrites. Quarantined records are durable but excluded from normal retrieval.

## Alternatives Considered

- Reject all suspicious text outright
- Silently sanitize and admit
- Delegate admission entirely to an LLM

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Admission is deterministic for the same request and policy version
- Quarantine never leaks into default search
- Every decision records reasons and warnings

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Safety-signal tests
- Quarantine retrieval exclusion test
- Policy-version receipt assertions

## Rollback Conditions

Set quarantine_on_safety_signal false only in an explicit compatibility policy and record that policy version.

## Supersedes / Superseded By

Replaces scattered validation and ad hoc write gates.

No later ADR supersedes this decision as of 2026-07-21.

## Amendments

**2026-09-04 — quarantine has a governed exit.** ADR-080 adds the review
path this decision left open: a scheduled `REVIEW_QUARANTINE` maintenance
operation consults an injected reviewer under a review policy, releases what
it clears through `MemoryService.transition_lifecycle` with the verdict as
evidence, and escalates only serious findings to a person. Admission itself
is unchanged and remains deterministic.
