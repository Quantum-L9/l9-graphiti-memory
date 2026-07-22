# ADR-022: Release, Publishing, and Rollback

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-022-release-publishing-and-rollback.md
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

The prior publish workflow could publish any buildable tag without requiring the full validation suite.

## Decision

Publishing is gated by tests, compile checks, assurance scanners, ADR validation, wheel build, and installed-wheel smoke tests. Tags use semantic versioning. Releases include source ZIP, wheel, sdist, manifest, change summary, and validation report.

## Alternatives Considered

- Publish from a developer laptop after manual checks
- Use mutable latest artifacts
- Treat wheel build success as release proof

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- No tag publish bypasses validation
- Artifacts have SHA-256 digests
- Rollback instructions and migration compatibility accompany every major release

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- CI workflow dependency graph
- Artifact digest verification
- Clean-environment install test

## Rollback Conditions

Reinstall the prior version and restore from the pre-migration database copy; v2 exports remain available for forward recovery.

## Supersedes / Superseded By

Supersedes build-only publishing.

No later ADR supersedes this decision as of 2026-07-21.
