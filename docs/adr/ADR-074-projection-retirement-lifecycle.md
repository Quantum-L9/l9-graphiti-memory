# ADR-074: Projection Retirement Lifecycle

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-074-projection-retirement-lifecycle.md
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

`ProjectionAdapter` had two operations: `project` and `erase`. `project` ran
when a record was admitted; `erase` ran only under verified privacy deletion.

Nothing ran when a record stopped being current. A superseded record kept its
projection, so a graph or semantic search continued to surface a fact the
canonical store had already replaced. An archived record kept its projection
too, so retention withdrew a record from canonical retrieval while the
derivation kept serving it. The projection and the canonical store disagreed,
and the projection won for any caller that searched it.

The only available remedy was `erase`, and reaching for it would have been
worse than the problem. Erasure carries privacy semantics: a deletion receipt,
a tombstone digest, redaction of canonical content, and an audit trail asserting
that content was destroyed on request. Superseded and archived records must keep
their content — that is what bi-temporal memory is for. Using the erasure path
for lifecycle transitions would have produced deletion receipts for records
nobody asked to delete and destroyed the history the archive was preserving.

## Decision

The projection lifecycle has three operations, not two.

**project** — the record is current; make it retrievable in the derivation.

**retire** — the record is no longer current, because it was superseded or
archived. Withdraw the projection so retrieval stops surfacing it. The canonical
record keeps its content, evidence, provenance, and lifecycle history. No
deletion receipt, no tombstone, no redaction. The projection remains rebuildable
from canonical state.

**erase** — verified privacy deletion. Destroy the projected copy under a
`DeletionReceipt`, alongside canonical redaction.

`MemoryService` emits a `memory.record.retire` outbox event in the same
transaction as the canonical transition that caused it: alongside the
supersession status events in `write`, and alongside the archive status events
in `apply_retention`. The transition and the retirement intent commit together
or not at all, so the two cannot diverge.

`OutboxWorker` handles `memory.record.retire` by calling `projection.retire`
and deleting the projection link. This handler never touches canonical record
state and never calls `complete_deletion`. A record with no projection link has
nothing to withdraw, so retirement is already satisfied and the event settles as
delivered rather than dead-lettering.

Graphiti exposes no native "mark inactive" primitive; `delete_episode` is its
only removal operation. `GraphitiProjection.retire` therefore calls the same
provider tool as `erase`. That shared primitive is the full extent of the
overlap. The operations differ in what they are permitted to touch, what
receipts they produce, and what survives: retirement leaves canonical content
whole and the projection rebuildable, erasure does not. A provider that later
offers a genuine deactivation primitive can implement `retire` against it
without any change above the adapter.

## Alternatives Considered

- Reuse `erase` for supersession and archive
- Leave stale projections in place and filter them at read time
- Re-project superseded records with a status marker instead of withdrawing them
- Add a distinct `retire` operation with its own outbox event type

## Rejected Alternatives

- Reusing `erase` would emit privacy deletion receipts for records nobody asked
  to delete and would redact the canonical history archiving exists to preserve.
- Read-time filtering requires resolving every projection hit against canonical
  state before returning it, which discards the latency benefit the projection
  exists to provide, and still leaves the provider index wrong for any consumer
  that queries it directly.
- Re-projecting with a status marker depends on every provider supporting
  queryable status and every query filtering on it; Graphiti offers no such
  guarantee, so stale facts would still surface.

## Invariants

- Supersession and archive emit retirement intent in the same transaction as
  the canonical transition
- Retirement never redacts canonical content or produces a deletion receipt
- Retirement never transitions a record to `DELETED`
- Erasure remains reachable only through verified deletion
- A record with no projection link retires successfully
- Projections stay rebuildable from canonical state after retirement

## Consequences

Positive: The projection stops contradicting the canonical store. Retention and
supersession have a lifecycle path that does not borrow privacy machinery.
Deletion receipts again mean only what they say.

Negative: Supersession and archive now generate projection traffic, so a bulk
retention run enqueues one retirement per archived record. Where a provider has
no deactivation primitive, retirement removes the projected episode, so
re-activating an archived record requires re-projection rather than a flag flip.

## Security Impact

Retirement narrows exposure: superseded and archived content stops being served
from the external provider while remaining available in the access-controlled
canonical store. It is not a privacy control and must not be presented as one —
only `erase` under a verified deletion receipt makes that claim.

## Migration Impact

Existing deployments carry projections for records already superseded or
archived. Those were created before retirement existed and are not retired
retroactively by this change; they are withdrawn by rebuilding the projection
from canonical state, which projects only active records. No canonical data
changes.

## Validation Requirements

- Tests prove supersession emits retirement intent atomically with the
  canonical transition, and that a failed commit leaves neither
- Tests prove the worker retires the superseded projection and drops its link
- Tests prove archive retires while canonical content, evidence, and state are
  preserved and no deletion receipt exists
- Tests prove verified deletion still erases and tombstones
- Tests prove retirement of an unprojected record settles as delivered

## Rollback Conditions

Reverting restores stale projections for superseded and archived records.
Retirement events already delivered have removed provider episodes; those
records are restored to the projection by a rebuild, not by the rollback.

## Supersedes / Superseded By

Extends ADR-025 (projections are rebuildable derivations) and narrows ADR-057
(verified erasure) to privacy deletion only.

No later ADR supersedes this decision as of 2026-08-20.
