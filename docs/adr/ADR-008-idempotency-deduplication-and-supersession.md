# ADR-008: Idempotency, Deduplication, and Supersession

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-008-idempotency-deduplication-and-supersession.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-04
/L9_META -->


**Date:** 2026-07-21
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2+

## Status

Accepted

## Context

Legacy code used search heuristics to discover near duplicates and sometimes retried without supersedes metadata. That made replay behavior nondeterministic.

## Decision

Writes use an explicit idempotency key. Exact replay of that key returns the original record ID. (The digest-derived fallback originally specified here was withdrawn by ADR-071: retry identity is explicit, and a write without a key is a distinct operation.) Corrections create new records and append supersession state events; prior truth is never overwritten.

## Alternatives Considered

- Use vector similarity as the idempotency mechanism
- Update records in place
- Let adapters decide retry semantics

## Rejected Alternatives

The alternatives above are rejected because they duplicate authority, hide failure, couple the package to one runtime or provider, or cannot be validated without weakening the canonical contracts.

## Invariants

- Same tenant, namespace, and explicit idempotency key resolves to one record
- Supersession preserves the old record and lineage
- Retries never create duplicate outbox effects

## Consequences

Positive: behavior has one owner, failures are observable, and adapters can evolve without redefining memory law.

Negative: the design requires explicit contracts, receipts, and migration work instead of relying on provider defaults or convenient shortcuts.

## Security Impact

This decision reduces implicit authority and makes security-relevant state inspectable. Threat modeling must cover tenant isolation, identity spoofing, replay, secret exposure, and failure-mode confusion where applicable.

## Migration Impact

Migration is compatibility-first: preserve externally valid command and protocol behavior, translate legacy data through versioned adapters, and cut over only after deterministic regression and installed-artifact validation.

## Validation Requirements

- Concurrent/replay tests
- Unique index validation
- Supersession history tests

## Rollback Conditions

Export duplicate receipts and replay through the canonical service using preserved idempotency keys.

## Supersedes / Superseded By

Replaces search-before-write duplicate guessing.

No later ADR supersedes this decision as of 2026-07-21.

## Amendments

**2026-09-04 — replay identity under drift, races, and non-current targets.**

The forensic codebase audit (findings F-07, F-09, F-10) narrowed three edges of
this decision:

- A replay carrying the same key and a different payload returned `DUPLICATE`
  with no signal. It still resolves to the original record, and the receipt now
  carries a warning that the replayed payload differs from the stored record,
  so a caller that changed its content under an old key can see it.
- Two retries racing between the duplicate lookup and the commit surfaced the
  unique index violation as a generic `StoreError`. The adapters raise the
  typed `IdempotencyConflict`; the service catches it, reads the record the
  index chose, and returns the `DUPLICATE` receipt this decision promises.
- Supersession accepted any target state, so a tombstone, a quarantined
  candidate, or a record already pending deletion could be "corrected".
  Only `ACTIVE`, `SUPERSEDED`, and `ARCHIVED` records can be superseded; any
  other target is an `AdmissionError`.

**2026-09-04 — conflicts are recorded links.** ADR-081 populates
`conflicts_with` through governed reconciliation; the conflict report that
guards phase locks and promotion now reads those links instead of recomputing
assertion overlaps on every call, and supersession of either side resolves
the conflict.
