# ADR-037: Configuration Authority and Drift Prevention

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-037-configuration-authority-and-drift-prevention.md
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

Scattered defaults caused project and scope mismatches in the original repo. The v0.2 package duplicated registry locations.

## Decision

MemorySettings and packaged resources are the canonical defaults. YAML and environment overrides follow a documented precedence. A drift scanner flags hardcoded security-sensitive defaults outside configuration modules.

## Alternatives Considered

- Let each module read arbitrary environment variables
- Store defaults only in documentation
- Duplicate config constants for convenience

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- One field has one default owner
- Security-sensitive lists are typed
- Configuration source is reported

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Config precedence tests
- Drift scanner
- Example config validation

## Rollback Conditions

Use an explicit YAML file matching the prior values while the canonical defaults are corrected.

## Supersedes / Superseded By

Harvests ADR-0098 and config mismatch detection.

No later ADR supersedes this decision as of 2026-07-21.
