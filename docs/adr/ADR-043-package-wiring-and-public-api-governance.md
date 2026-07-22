# ADR-043: Package Wiring and Public API Governance

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-043-package-wiring-and-public-api-governance.md
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

Legacy packs contained many useful but unwired files. Documentation often counted existence as implementation.

## Decision

Public modules are intentionally exported, consumed, tested, or declared entrypoints. An AST wiring audit identifies orphan modules and unused API. New modules without a runtime, CI, or operator path fail review.

## Alternatives Considered

- Allow speculative modules for future use
- Depend on manual grep
- Export every symbol from package root

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Feature existence requires reachable wiring
- Public API stays small
- Tests alone do not prove production wiring

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- audit_package_wiring.py
- Entrypoint import tests
- Manifest owner map review

## Rollback Conditions

Move an experimental module to a separate branch or design document until it has a real consumer.

## Supersedes / Superseded By

Harvests package wiring audits from L9_Original_Repo.

No later ADR supersedes this decision as of 2026-07-21.
