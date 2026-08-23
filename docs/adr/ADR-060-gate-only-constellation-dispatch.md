# ADR-060: Gate-Only Constellation Dispatch

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-060-gate-only-constellation-dispatch.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-22
**Decision owner:** Quantum-L9 architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.2+

## Status

Accepted

## Context

ADR-026 named the shared constellation transport boundary but v2.1 contained no executable adapter proving immutable derivation, trace preservation, lineage preservation, or Gate-only egress.

## Decision

Provide a generic constellation bridge that accepts the canonical packet model and Gate client through injected protocols. Root work is created by the owning packet factory. Follow-up work is produced only through `derive_or_with_hop`. The bridge sends packets only to Gate and exposes no destination, peer URL, node registry, or direct node dispatcher.

## Alternatives Considered

- Define a local copy of the shared transport model
- Let callers select a destination node
- Send memory requests directly to peer services

## Rejected Alternatives

All alternatives duplicate authority or bypass Gate routing and admission.

## Invariants

- Parent packets are never mutated in place
- Trace identifiers are preserved across follow-up hops
- Lineage grows for each follow-up
- Gate receipts match the dispatched packet
- Gate alone resolves destination

## Consequences

Positive: inter-node alignment is executable and provider-neutral. Negative: consumers must inject the canonical packet factory and Gate client.

Implementation binding (RP-002): inject `CanonicalGateClient` from
`constellation-node-sdk` `v1.0.1`. `HealthReport.gate` is additive so Gate
unavailable is `PARTIAL` + `gate is unavailable` and does not mark the
canonical store failed.

## Security Impact

The bridge removes caller-selected routing and makes trace and lineage drift fail closed.

## Migration Impact

Existing non-constellation consumers are unaffected. L9 node consumers replace direct peer calls with the bridge.

## Validation Requirements

- Root dispatch behavior test
- Follow-up trace and lineage tests
- In-place mutation rejection test
- Static scan for peer URLs and destination fields

## Rollback Conditions

Rollback requires disabling the L9 constellation integration, not restoring direct peer dispatch.

## Supersedes / Superseded By

Operationalizes ADR-026. No later ADR supersedes this decision.
