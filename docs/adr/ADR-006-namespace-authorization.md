# ADR-006: Namespace Authorization

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-006-namespace-authorization.md
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

The old MCP server trusted caller-supplied group_id values. Remote clients could potentially select another repository namespace.

## Decision

Authenticated MemoryPrincipal claims are established server-side. NamespacePolicy evaluates read, write, promote, archive, and administration independently. Requested namespaces are intersected with claims; identity fields in payloads are ignored. Local CLI and stdio principals are repository-scoped or explicitly configured, and administrator authority is disabled unless `local_is_admin` is deliberately enabled.

## Alternatives Considered

- Authorize by group_id format
- Use one global namespace
- Trust local network location as identity

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Caller identity is never writable by the request body
- Read authority does not imply write authority
- No cross-tenant record is returned even if record ID is known
- Local and stdio operation never imply wildcard or administrator authority

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Auth token integration tests
- Cross-tenant get/search tests
- MCP spoofing tests
- Local and stdio no-implicit-admin tests

## Rollback Conditions

Fall back to loopback-only local mode with an explicit local principal; remote unauthenticated mode remains prohibited.

## Supersedes / Superseded By

Replaces caller-chosen group authorization.

No later ADR supersedes this decision as of 2026-07-21.
