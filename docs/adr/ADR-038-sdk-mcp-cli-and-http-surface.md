# ADR-038: SDK, MCP, CLI, and HTTP Surface

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-038-sdk-mcp-cli-and-http-surface.md
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

The original monolith accumulated hundreds of routes. The standalone repository needs several access modes without duplicating logic.

## Decision

Python callers use MemoryService or the shipped thin MemorySDK. Agents use MCP. Operators use CLI. HTTP is restricted to MCP transport, health, and readiness. All surfaces share the composition root and server-derived identity. Stdio MCP resolves a repository-scoped local principal or uses explicit local namespace claims; it does not receive wildcard administrator rights by default.

## Alternatives Considered

- Expose one HTTP route per service method
- Require Python SDK for non-Python agents
- Place business logic in command handlers

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Adapters are thin
- Remote HTTP requires authentication by default
- Loopback unauthenticated mode is explicit
- Stdio namespace grants and administrator authority are explicit

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Surface smoke tests
- MCP auth tests
- CLI installed-wheel tests
- Stdio namespace-claim tests

## Rollback Conditions

Retain stdio MCP and CLI while disabling HTTP; core service remains unchanged.

## Supersedes / Superseded By

Adapts SDK-first lessons from L9_Original_Repo.

No later ADR supersedes this decision as of 2026-07-21.
