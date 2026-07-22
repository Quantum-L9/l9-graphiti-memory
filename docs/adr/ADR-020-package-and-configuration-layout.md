# ADR-020: Package and Configuration Layout

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-020-package-and-configuration-layout.md
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

The v0.2 wheel omitted its registry and operational assets, causing installed CLI failure. Runtime code looked for files outside the package.

## Decision

Python runtime resources live under l9_graphite_memory/resources and are declared as package data. Root config files are operator examples. Source, hooks, docs, tests, tools, and scripts ship in the source distribution and release ZIP.

## Alternatives Considered

- Load config only from the git checkout
- Copy every repository file into site-packages
- Fetch defaults from the network

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Installed-wheel resolve works without checkout
- Runtime defaults have one canonical packaged location
- Operator overrides are explicit paths or environment variables

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Wheel install smoke test
- importlib.resources test
- Manifest comparison

## Rollback Conditions

Install v0.2 in a separate environment and point it at an exported legacy registry; do not overwrite the v2 data directory.

## Supersedes / Superseded By

Fixes the broken v0.2 wheel layout.

No later ADR supersedes this decision as of 2026-07-21.
