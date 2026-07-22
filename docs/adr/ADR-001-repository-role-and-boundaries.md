# ADR-001: Repository Role and Boundaries

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-001-repository-role-and-boundaries.md
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

The previous repository mixed a memory library, an MCP service, Cursor hooks, transport clients, and legacy extractors. Packs from L9-Ops-MCP and L9_Original_Repo also attempted to own memory orchestration outside this repository, creating duplicate control planes.

## Decision

This repository is the canonical, domain-agnostic memory control plane. It owns memory contracts, authorization, admission, canonical persistence, retrieval, curation, receipts, MCP/CLI adapters, and compatibility hooks. It does not own agent execution, world-model reasoning, checkpoint orchestration, business-domain logic, or constellation routing.

## Alternatives Considered

- Keep memory embedded in each consuming agent repository
- Rebuild the full L9 AI operating system inside this repository
- Treat this repository as a thin Zep client only

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- No consumer may implement a competing durable memory write path
- Core memory code remains independent of Cursor, Claude, and any business domain
- External projections are adapters, never the canonical source of truth

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Run package wiring audit
- Run memory bypass scanner
- Review public imports and MCP inventory

## Rollback Conditions

Rollback means restoring the v1 compatibility branch while preserving the v2 database and receipts for later replay.

## Supersedes / Superseded By

Supersedes the ambiguous standalone-subsystem framing in the v0.2 repository.

No later ADR supersedes this decision as of 2026-07-21.
