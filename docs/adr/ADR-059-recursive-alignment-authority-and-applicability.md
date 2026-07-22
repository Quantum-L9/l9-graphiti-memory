# ADR-059: Recursive Alignment Authority and Applicability

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-059-recursive-alignment-authority-and-applicability.md
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

The active recursive-alignment kernel contains rules for runtime nodes, Gate, shared transport, service packs, and tracked-file provenance. This repository is a dependency package with optional operator, provider, service, and constellation adapters. Applying node-only rules to every internal memory call would duplicate shared infrastructure, while ignoring the inter-node rules would leave a false architecture claim.

## Decision

Classify the repository as a dependency package with an SDK facade and optional service adapters. Apply TransportPacket and Gate rules only when memory intent crosses an L9 constellation boundary. Apply memory-domain contracts internally. Apply chassis, HTTP authentication, provider transport, and CI rules at their explicit adapter or repository-root layers, never inside the canonical memory engine.

## Alternatives Considered

- Treat the package as a runnable constellation node
- Ignore the recursive-alignment kernel because the package is not a node
- Replace all internal memory contracts with the shared transport contract

## Rejected Alternatives

The alternatives either duplicate shared infrastructure, erase domain typing, or leave inter-node egress ungoverned.

## Invariants

- The canonical memory engine owns domain logic only
- Inter-node work uses the injected shared transport model and Gate
- Provider adapters are not misclassified as L9 nodes
- Applicability decisions are explicit and testable

## Consequences

Positive: strict L9 boundaries are enforced where they apply without contaminating internal memory law. Negative: reviewers must understand the package-versus-node distinction.

## Security Impact

The decision reduces accidental routing authority and prevents service or provider credentials from entering the memory engine.

## Migration Impact

Existing CLI, MCP, SDK, and provider integrations remain valid. New L9 node integrations must use the constellation bridge.

## Validation Requirements

- Recursive alignment assurance check
- Layer-boundary import check
- Repository classification in `ALIGNMENT.md`

## Rollback Conditions

Rollback is allowed only if a superseding architecture contract reclassifies the repository and provides equivalent boundary tests.

## Supersedes / Superseded By

Clarifies ADR-001 and ADR-026. No later ADR supersedes this decision.
