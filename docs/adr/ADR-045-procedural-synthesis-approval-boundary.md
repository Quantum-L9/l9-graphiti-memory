# ADR-045: Procedural Synthesis Approval Boundary

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-045-procedural-synthesis-approval-boundary.md
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

The original repo generated heuristic candidates from traces and correctly avoided automatic application. The memory packs proposed procedural promotion.

## Decision

Procedural synthesis is an optional curation producer. It emits candidates with conditions, actions, confidence, source record IDs, and synthesis receipt. Promotion into procedural memory requires the normal default-deny PromotionPolicy.

## Alternatives Considered

- Auto-apply high-confidence heuristics
- Ban synthesis entirely
- Store every candidate as an active procedure

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Candidate generation is not approval
- Sources remain traceable
- No synthesized procedure changes runtime code

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Candidate schema tests
- Promotion gate tests
- No auto-apply scan

## Rollback Conditions

Archive candidates and disable the synthesis worker; existing approved procedures remain intact.

## Supersedes / Superseded By

Harvests ProceduralSynthesis without self-modification.

No later ADR supersedes this decision as of 2026-07-21.
