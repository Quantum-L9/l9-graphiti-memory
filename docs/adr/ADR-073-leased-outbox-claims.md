# ADR-073: Leased Outbox Claims

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-073-leased-outbox-claims.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-08-20
/L9_META -->


**Date:** 2026-08-20
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.3+

## Status

Accepted

## Context

`claim_outbox` moved due events to `PROCESSING` and returned them. Nothing ever
moved them back. A worker that died between claiming an event and settling it —
container eviction, deploy, OOM kill, lost database connection — left that event
in `PROCESSING` permanently. No later claim cycle selected it, because the claim
query only looked at `PENDING` and `RETRY`.

The record itself stayed canonical, so no memory was lost. But its projection
was never delivered and never retried, and the event was not visible as failed:
it counted toward `outbox_backlog` but never reached the terminal `DEAD` state
an operator watches for. The only recovery was a manual `UPDATE`.

Claiming was also unsafe under concurrency. Two workers polling the same store
could select the same rows before either wrote `PROCESSING`, so both would
deliver the same projection and both would write a locator. With the shared
backend (ADR-072) making multiple workers the normal deployment, this stopped
being hypothetical.

## Decision

A `PROCESSING` claim is a time-bounded lease, not ownership in perpetuity.

`OutboxEvent` carries `lease_id`, `lease_owner`, and `lease_expires_at`.
`claim_outbox(limit, now, lease_seconds, lease_owner)` selects events that are
either due (`PENDING`/`RETRY` with `next_attempt_at <= now`) or abandoned
(`PROCESSING` with `lease_expires_at <= now`), and stamps each with a fresh
lease. An abandoned event therefore rejoins the normal retry path on the next
cycle rather than being stranded.

`update_outbox` takes the `lease_id` the caller was granted and rejects the
write when it no longer matches, so a revived worker cannot overwrite the
outcome of the worker that recovered its event. Settling clears the lease.

On PostgreSQL, claims use `FOR UPDATE SKIP LOCKED`, which makes two concurrent
claim cycles disjoint: a row another transaction is already claiming is passed
over rather than waited on.

`OutboxWorker` identifies itself as `{hostname}:{pid}`, holds the lease across
delivery, and reports lost leases as a `lease_lost` count rather than forcing
its outcome. Lease duration is `outbox_lease_seconds` (default 300) and must
exceed the slowest expected projection call.

## Alternatives Considered

- Sweep `PROCESSING` events older than a threshold back to `RETRY` on a timer
- Hold a database row lock for the duration of delivery
- Use an external queue with its own visibility-timeout semantics
- Make the claim itself a lease with a CAS-guarded settle

## Rejected Alternatives

- A separate sweeper is a second process that can itself die, and it cannot
  distinguish a slow live worker from a dead one, so it either reclaims events
  still being delivered or waits too long to matter.
- Holding a lock across delivery ties a database connection to a network call
  to an external provider, so a hung provider exhausts the connection pool.
- An external queue would put delivery state outside the canonical store and
  break the atomicity ADR-018 depends on: the outbox event must commit in the
  same transaction as the record it projects.

## Invariants

- A claimed event always carries a lease id, owner, and expiry
- An event with a live lease is not claimable by another worker
- An event whose lease has expired is claimable again
- A settle with a stale lease id is rejected, not silently applied
- Settling clears the lease so the event can be claimed again if it retries
- Concurrent claim cycles on the shared backend are disjoint

## Consequences

Positive: A crashed worker costs at most one lease interval of delay instead of
stranding a projection forever. Multiple workers can run against one shared
store safely. Lost leases are observable rather than silent.

Negative: A worker whose delivery legitimately outruns the lease will have its
event recovered by another worker and its own settle rejected, so
`outbox_lease_seconds` must be tuned above the slowest projection call.
Recovery can therefore deliver a projection twice; projections are idempotent
by locator (ADR-025), so this converges rather than corrupting.

## Security Impact

`lease_owner` records a hostname and process id in the canonical store. This is
operational metadata, not memory content, and is already implied by existing
audit fields.

## Migration Impact

Both SQL adapters add three nullable columns and bump the store schema version
to 5. Existing rows migrate in place with `ALTER TABLE ... ADD COLUMN`; a
pre-existing `PROCESSING` row has a null `lease_expires_at`, which is treated as
expired and is therefore recovered on the first claim cycle after upgrade. That
is the intended outcome: those events were stranded.

## Validation Requirements

- Tests prove a claim grants a bounded lease on every backend
- Tests prove a live lease is not reclaimable
- Tests prove an abandoned claim recovers only after expiry
- Tests prove a stale worker's settle is rejected while the new owner's succeeds
- A concurrency test proves independent threads on the shared backend claim
  disjoint sets and strand nothing

## Rollback Conditions

Reverting restores permanent `PROCESSING` stranding. Events already carrying
leases would be ignored by the reverted claim query and would need manual
requeueing.

## Supersedes / Superseded By

Extends ADR-018. The outbox remains the post-commit projection delivery
mechanism; this decision only makes its claims recoverable.

No later ADR supersedes this decision as of 2026-08-20.
