# ADR-026: TransportPacket Constellation Boundary

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-026-transportpacket-constellation-boundary.md
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

Older L9 material used a deprecated universal envelope at inter-node boundaries. Current L9 doctrine identifies TransportPacket as the constellation transport contract.

## Decision

This repository does not define or own TransportPacket. L9 node adapters use the injected canonical constellation transport through `GateMemoryBridge` at their boundary. MemoryRecord remains an internal domain contract.

## Alternatives Considered

- Rename MemoryRecord to TransportPacket
- Continue exporting the deprecated universal envelope as law
- Import node runtime code into this package

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- No node-to-node routing logic lives here
- Transport wrappers do not alter memory authorization
- Memory contracts remain usable outside L9

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Dependency scan for node imports
- Root and follow-up Gate dispatch tests
- Trace, lineage, and immutable-derivation tests
- No deprecated universal-envelope exports in the core API

## Rollback Conditions

Keep compatibility parsing at the external adapter while preserving the internal v2 contract.

## Supersedes / Superseded By

Supersedes universal-envelope-as-everything assumptions from L9_Original_Repo.

ADR-060 operationalizes this decision without transferring ownership of the shared transport model.
