# ADR-036: Canonical Write Bypass Enforcement

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-036-canonical-write-bypass-enforcement.md
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

Direct SQL, provider calls, and subprocess writes repeatedly bypassed validation and governance in older systems.

## Decision

A release-blocking assurance scanner detects direct commit, SQL mutation, and provider write patterns outside approved storage and service modules. Exceptions require an explicit reviewed manifest entry with rationale and expiry.

## Alternatives Considered

- Rely on reviewer memory
- Allow inline bypass comments anywhere
- Ban all SQL including migrations

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Public adapters never call RecordStore.commit_write
- Migrations are isolated from runtime code
- Exceptions are visible and temporary

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Run check_memory_write_bypass.py
- Negative fixture test
- Review approved_bypasses.yaml

## Rollback Conditions

Disable a false-positive rule with a narrow manifest entry; do not delete the enforcement gate.

## Supersedes / Superseded By

Harvests GMP-129 bypass detection and strengthens it.

No later ADR supersedes this decision as of 2026-07-21.
