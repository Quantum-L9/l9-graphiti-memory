# ADR-079: Governed Write Phase-Lock Atomicity

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-079-governed-write-phase-lock-atomicity.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-04
/L9_META -->


**Date:** 2026-08-27
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.3+

## Status

Accepted

## Context

`MemoryService.write_governed()` verified a phase lock and then committed
through a separate call:

```python
verification = self.verify_phase_lock(principal, request.namespace, task_signature)
if not verification.valid:
    raise AuthorizationError(...)
return self.write(principal, request)
```

`verify_phase_lock()` compares the lock's `snapshot_digest` against the
namespace's current conflict-report digest. Both reads happen before the store
is asked to commit anything.

Between that comparison and `commit_write`, any concurrent writer sharing the
store can change the namespace: a second governed request, a second server
process, or an ordinary canonical write from an unrelated path. Two governed
requests could each verify against the same snapshot and each admit a record,
when the first commit should have invalidated the lock for the second.

This is a time-of-check/time-of-use gap, not a hypothetical. Nothing in the
path serialized the two steps. The phase lock read as an authorization, but it
only ever described a moment that had already passed by the time the write
landed.

Raised as issue #38, deferred out of PR #35 because a correct fix changes a
port contract and warrants its own decision record.

## Decision

The snapshot comparison moves inside the transaction that commits the write.

`RecordStore.commit_write()` accepts an optional `expected_phase_lock`
precondition. When present, the implementation must re-verify its
`expected_snapshot_digest` against the namespace's live active records inside
the committing transaction, and raise `PhaseLockSnapshotConflict` when it no
longer matches. This mirrors the `expected_version` precondition the
active-memory `put_context` contract already uses.

`write_governed()` keeps its up-front verification — it still produces the
caller-facing `AuthorizationError` for a missing, expired, or foreign lock —
and now passes the verified digest through to the store, which is what
actually closes the window.

The digest helper moves to `l9_graphite_memory.ports.phase_lock.snapshot_digest`
so the service and all three adapters compute an identical value. That module
depends only on `contracts` and on the dependency-free normalization helpers,
so it adds no layering cycle.

Per-adapter serialization:

- **in-memory** — a `threading.RLock` makes the re-check and the mutation one
  critical section.
- **sqlite** — `BEGIN IMMEDIATE` already holds the write lock when the re-read
  runs, so no writer can overtake the transaction before it commits.
- **postgres** — a transaction-scoped advisory lock keyed on
  `tenant_id/namespace`, taken before the re-read. `SELECT ... FOR UPDATE`
  alone would lock only rows that already exist, so a concurrent governed
  write inserting a *new* record would not be excluded. The re-read then also
  catches non-governed writers, which never take the advisory lock but do
  change the digest.

The precondition is enforced on the path that admits a record. Receipt-only
commits (duplicate and rejected admissions, where `record is None`) do not
change the namespace snapshot and are not gated, so a governed no-op cannot
raise a spurious conflict.

## Alternatives Considered

Retrying the verification immediately before `commit_write`, still outside the
transaction. This narrows the window without closing it and would have made the
remaining race far harder to reproduce.

Serializing all governed writes behind a single global lock. Correct, but it
serializes unrelated namespaces and turns an isolated correctness fix into a
throughput ceiling.

Raising the postgres isolation level to `SERIALIZABLE` for governed writes.
This closes the phantom case without an advisory lock, but it pushes retry
handling onto every caller and changes failure semantics for a much wider set
of transactions than this decision needs.

## Rejected Alternatives

Leaving the check where it was and documenting the race. The phase lock exists
to authorize a write; an authorization that can be stale at the moment it is
used is not an authorization.

Computing the snapshot digest inside each adapter independently. Three
implementations of one digest is three opportunities for them to disagree,
and a disagreement would present as a permanent spurious conflict.

## Invariants

- A governed write that carries a phase-lock precondition is admitted only if
  the namespace snapshot inside the committing transaction still equals the
  digest the lock was verified against.
- The service and every record store compute a namespace snapshot digest
  identically, via `ports.phase_lock.snapshot_digest`.
- A store that cannot honour the precondition must fail the write rather than
  admit it.
- `PhaseLockSnapshotConflict` is a `StoreError`, so existing store-failure
  handling paths remain correct without change.

## Consequences

Governed writes can now fail with `PhaseLockSnapshotConflict` where they
previously succeeded against a stale lock. That is the intended behaviour
change: the failure surfaces a race that was previously silent data admission.

Callers that treat a governed write as infallible need to handle the conflict,
re-acquire the phase lock, and retry. The error message carries both the
expected and the current digest.

The postgres path takes one additional advisory lock per governed write.
Contention is scoped to a single `tenant_id/namespace` pair.

Ungoverned `write()` is unchanged and takes no precondition.

## Security Impact

Closes a path by which a record could enter a namespace under an authorization
that was no longer valid. The phase lock is an authorization construct, so a
stale-lock admission is an authorization defect, not only a consistency one.

No credential, transport, or principal-resolution behaviour changes. The
conflict message contains only digests, never record content.

## Migration Impact

No data migration and no schema change. The new port parameter is keyword-only
with a `None` default, so any existing `RecordStore` implementation that does
not accept it keeps working for ungoverned writes; it will not enforce the
precondition, which is why all three in-tree adapters implement it.

Stored `PhaseLockReceipt` values are unchanged and remain valid.

## Validation Requirements

`tests/conformance/test_phase_lock_write_atomicity.py`, parameterized over
`STORE_BACKENDS`, drives a competing canonical write into the window between
verification and commit and asserts the governed write is refused. The suite
fails against an implementation that only checks before the transaction, which
was confirmed by reverting the precondition pass-through and observing
`DID NOT RAISE`.

The postgres leg runs whenever `L9_MEMORY_TEST_POSTGRES_DSN` is configured and
skips loudly otherwise, so a missing database narrows the matrix visibly rather
than silently.

## Rollback Conditions

Roll back if the precondition produces conflicts for writes that are not
actually racing — most plausibly a digest disagreement between the service and
one adapter. The symptom would be a governed write that fails repeatedly with
identical expected and current digests in the message.

Rollback is passing `expected_phase_lock=None` from `write_governed`, which
restores the prior behaviour without touching the store implementations.

## Supersedes / Superseded By

Supersedes nothing. Not superseded.

Refines the governed-write path introduced alongside the phase-lock contract
and complements ADR-072's shared canonical backend, under which concurrent
writers sharing one store are the expected deployment rather than an edge case.

## Amendments

**2026-09-04 — the snapshot is the complete active set.**

The forensic codebase audit (finding F-06) found the rollback symptom this ADR
predicted, from a cause it did not: `MemoryService.conflicts` built its digest
from `list_records` with the store's default bound of 1,000 records, while
every adapter re-verified the precondition over the whole active set. Past
that bound the two digests could never agree and every governed write in the
namespace failed with `PhaseLockSnapshotConflict`. `list_records` now accepts
`limit=None`, the service digests the unbounded listing, and
`tests/conformance/test_phase_lock_snapshot_scale.py` drives a governed write
through a namespace of 1,001 records on every backend.
