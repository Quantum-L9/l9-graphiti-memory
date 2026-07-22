# ADR-053: Checkpoint Integrity Utility Boundary

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-053-checkpoint-integrity-utility-boundary.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-22
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.1+

## Status

Accepted

## Context

The legacy monolith mixed agent checkpoint orchestration into memory ingestion. The standalone memory package should not own agent lifecycle, yet consumers need a safe utility for verifying serialized checkpoint payloads.

## Decision

Provide a small CheckpointIntegrity utility that canonicalizes payloads, records schema and algorithm versions, computes SHA-256 integrity digests, and optionally uses HMAC for authenticity. Agent checkpoint scheduling, storage, restoration, and lifecycle remain outside this repository.

## Alternatives Considered

- Reintroduce checkpoint orchestration into MemoryService
- Use unsigned checksums as proof of authenticity
- Use pickle serialization

## Rejected Alternatives

- Checkpoint orchestration violates repository boundaries
- Checksums detect corruption but not malicious tampering
- Pickle is unsafe and non-portable

## Invariants

- Utility output is deterministic and versioned
- HMAC is required when authenticity is claimed
- No pickle or executable serialization
- The repository does not schedule or restore agent state

## Consequences

Positive: Consumers gain a reusable integrity primitive without ownership drift

Negative: Consumers remain responsible for secure key management and checkpoint lifecycle

## Security Impact

HMAC keys are external secrets and never persisted by the utility. Verification uses constant-time comparison.

## Migration Impact

Legacy unsigned checkpoints may be verified for integrity only and must be labeled unauthenticated.

## Validation Requirements

- Deterministic checksum tests
- HMAC tamper and wrong-key tests
- Boundary documentation checks

## Rollback Conditions

Remove the optional utility export; checkpoint payloads remain owned by consuming runtimes.

## Supersedes / Superseded By

Clarifies ADR-028 and ADR-016.

No later ADR supersedes this decision as of 2026-07-22.
