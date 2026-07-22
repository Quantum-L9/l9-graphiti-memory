# ADR-021: Testing and Adapter Conformance

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-021-testing-and-adapter-conformance.md
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

Earlier packs had Python and shell tests that were not invoked by the same runner, stale paths, environment skips, and signature-only checks.

## Decision

Deterministic CI includes unit, integration, regression, and conformance suites. Every RecordStore and ProjectionAdapter implementation must pass shared behavioral tests. Live provider tests are separate and never count as deterministic proof.

## Alternatives Considered

- Rely on smoke tests only
- Skip security tests when environment flags are off
- Maintain backend-specific expectations

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- No release-blocking invariant is skipped
- In-memory and SQLite stores share conformance tests
- Regression tests cover retired paths and aliases

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- pytest strict run
- wheel-installed smoke run
- shell syntax and assurance scanners

## Rollback Conditions

Revert the failing adapter while retaining the shared contracts and tests; no weakening of the conformance suite is allowed.

## Supersedes / Superseded By

Replaces disconnected shell and pytest validation.

No later ADR supersedes this decision as of 2026-07-21.
