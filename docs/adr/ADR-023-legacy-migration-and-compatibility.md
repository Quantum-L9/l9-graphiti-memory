# ADR-023: Legacy Migration and Compatibility

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-023-legacy-migration-and-compatibility.md
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

Existing consumers use l9-memory commands, Graphiti aliases, group registries, and episode-shaped data. A rewrite that breaks all surfaces would be operationally unsafe.

## Decision

Version 2 preserves CLI entrypoints, core command names, MCP aliases, hook JSON decisions, and legacy episode import. Internal behavior is replaced. Compatibility is tested and carries explicit deprecation metadata.

## Alternatives Considered

- Hard cutover with no aliases
- Freeze v0.2 behavior indefinitely
- Run v1 and v2 control planes against the same writable store

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Compatibility never bypasses v2 authorization or admission
- Legacy import is idempotent
- Removed behavior is documented with migration commands

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Compatibility matrix tests
- Legacy episode upcast test
- CLI alias smoke tests

## Rollback Conditions

Run v0.2 read-only against its own store while exporting episodes to v2. Never dual-write without idempotency receipts.

## Supersedes / Superseded By

Defines the transition from v0.2 to v2.0.

No later ADR supersedes this decision as of 2026-07-21.
