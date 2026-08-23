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

Implementation binding (RP-001): the authoritative package is
`constellation-node-sdk` published from `Quantum-L9/Gate_SDK`. This repository
pins `v1.0.1` (`>=1.0.1,<1.1.0`) via the optional `constellation` extra.
`CanonicalTransportPacketFactory` calls `create_transport_packet` for roots and
`TransportPacket.derive` for follow-ups. Unsupported SDK versions fail closed
with `UnsupportedTransportPacketVersion`. This repository still does not define
TransportPacket.

Implementation binding (RP-002): `CanonicalGateClient` wraps
`constellation_node_sdk.GateClient`. Callers pass only a packet. Destination
stays at the SDK default (`gate`). Hosting runtime supplies `GATE_URL`,
`L9_NODE_NAME`, and signing material. Dispatch receipts are the response
`TransportPacket` validated against the dispatched packet id / trace id.
Typed failures: denied, rejected, unavailable, timeout, malformed-receipt.
`send_to_gate` has no retry or circuit-breaker; this adapter does not add them.

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
