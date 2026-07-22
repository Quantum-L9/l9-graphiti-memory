# ADR-050: Phase-Lock Snapshot Verification

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-050-phase-lock-snapshot-verification.md
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

A conflict check can become stale immediately after a lock is issued. A lock that proves only that a check once ran can authorize work against a different memory snapshot.

## Decision

Bind every phase lock to a deterministic namespace snapshot digest, task signature, principal, policy version, and expiration. Verification recomputes the snapshot and fails when records, conflicts, policy, task, or time have changed.

## Alternatives Considered

- Trust a boolean phase_lock flag
- Check conflicts only at issuance
- Use a lock unrelated to task identity

## Rejected Alternatives

- Boolean flags provide no evidence
- Issuance-only checks allow stale authorization
- Unbound locks can be replayed across tasks

## Invariants

- Locks are granted only after successful conflict evaluation
- The snapshot digest covers the current governed namespace state
- Verification is required before task execution
- Changed snapshots invalidate existing locks

## Consequences

Positive: Locks become evidence-bearing and replay-resistant

Negative: Frequent writes can require lock renewal

## Security Impact

Snapshot binding reduces stale-decision and replay risk. Lock receipts contain identifiers and digests, not private content.

## Migration Impact

Legacy local phase-lock flags are compatibility hints only and do not substitute for service verification.

## Validation Requirements

- Grant, expiry, task mismatch, conflict, and snapshot-change tests
- CLI and MCP verification surface tests
- Hook-state regression tests

## Rollback Conditions

Invalidate all outstanding locks and require fresh issuance under the prior stable policy.

## Supersedes / Superseded By

Strengthens ADR-015 and ADR-019.

No later ADR supersedes this decision as of 2026-07-22.
