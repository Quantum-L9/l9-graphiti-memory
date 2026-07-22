# ADR-017: Hook and Agent Integration

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-017-hook-and-agent-integration.md
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

Extracted hooks still resolved Cursor-Governance paths and suppressed failures. This contradicted standalone packaging.

## Decision

Hooks call the installed l9-memory command or python -m l9_graphite_memory. A local receipt guard verifies typed, expiring hydration evidence only; it is not constellation Gate and owns no workflow. Prefetch failure is explicit and blocks only when write gates are enabled. Hooks remain optional compatibility adapters.

## Alternatives Considered

- Embed source-tree paths in every hook
- Make gate decisions depend on live network calls
- Remove hooks and require manual use

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Receipt-guard logic performs no network I/O or routing
- Hooks are shell-syntax validated
- State location is configurable and package-independent

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- bash -n checks
- Receipt-guard deny/allow tests
- Installed-wheel hook smoke test

## Rollback Conditions

Disable L9_MEMORY_WRITE_GATES and remove installed hooks; canonical memory remains usable through CLI/MCP.

## Supersedes / Superseded By

Replaces Cursor-Governance path coupling.

ADR-061 supersedes its local Gate terminology while preserving hook compatibility.
