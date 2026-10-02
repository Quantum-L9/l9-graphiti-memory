# ADR-084: Projection Runtime and Target-Aware Lifecycle

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-084-projection-runtime-and-target-aware-lifecycle.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-10-01
/L9_META -->

**Date:** 2026-10-01
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+

## Status

Accepted

## Context

ADR-063 introduced a deterministic projection manifest and compiler but left
the runtime with a single scalar projection: one `projection_backend`, one
adapter, one link per record keyed by `(record_id, projection_name)`. The
compiled `facts-v8` manifest names two provider targets, a Graphiti MCP target
and a Zep target, but nothing could execute it. A second target could not be
delivered, retired, erased, or rebuilt independently, and a failure at one
provider could not be told apart from a failure at the other.

The canonical store remains the source of truth. Each provider copy is still a
derived, disposable projection (ADR-063, ADR-074), and deletion still has to
erase every durable copy before it completes (ADR-057).

## Decision

1. **Target modes.** Every manifest provider declares `mode`: `active`,
   `shadow`, or `disabled`. The default is `disabled`, so an undeclared mode
   never receives data. `required` is allowed only on active targets. The
   manifest status must agree with its targets: `active` needs at least one
   active target, `shadow` forbids active targets, `retired` permits only
   disabled targets. The mode is part of the compiled target and therefore of
   the manifest digest.
2. **ProjectionRuntime.** `projections.runtime.ProjectionRuntime` is the one
   executable view of the compiled targets. Each `ProjectionTargetBinding`
   carries the target identity (`name:vN:provider-type:target`), mode,
   required flag, adapter, and manifest and render-contract digests. It has no
   store access. A legacy runtime wraps one scalar adapter as a single active
   target whose identity is the adapter name, so existing links and outbox
   events resolve unchanged.
3. **Explicit runtime selection.** `projection_runtime` is `legacy` (default)
   or `manifest`. Manifest mode requires `projection_manifest`, and is mutually
   exclusive with a non-`none` `projection_backend` and with the legacy
   `projection_required` policy. Nothing is inferred from the presence of a
   manifest file.
4. **Factory-built targets.** `adapters.factory.build_projection_runtime`
   builds one adapter per target from the existing adapter and transport
   architecture: `graphiti_mcp` through `HttpMcpTransport`, `zep` through
   `ZepCloudTransport`, both wrapped by the unchanged `GraphitiProjection`.
   There is no composite adapter. Only a target named `primary` binds the
   existing scalar credentials; a delivering target without configuration
   fails closed at startup, and an unconfigured disabled target is bound with
   no adapter.
5. **Target-aware links and receipts.** `ProjectionLink` is keyed by
   `(record_id, target_identity)` and records projection version, provider
   type, and both digests. Retirement receipts record the target. Rebuild
   receipts report candidates per target. Deletion receipts list every
   erase event and target.
6. **One outbox intent per target.** Writes, lifecycle transitions, and
   retention emit one `project` or `retire` event per delivering target, and
   every payload names its `target_identity`. The worker resolves that target,
   delivers or retires only there, and saves or removes only that target's
   link. An event without a target identity, written before this ADR, resolves
   only when the runtime has exactly one target and otherwise fails closed.
7. **Stale-event safety.** A project event re-reads canonical state at
   delivery and after projection; a record that stopped being active is
   retired from that target instead of resurrected.
8. **Target-complete deletion.** Deletion emits one `erase` event per copy
   holder: every delivering target plus every target, disabled or not, that
   still holds a link. A target's link is removed only after its verified
   erase. The store refuses `complete_deletion` while any link remains, so a
   partial erase leaves the record `DELETION_PENDING` and retryable.
9. **Target-aware rebuild.** `rebuild_projection` computes candidates per
   delivering target and accepts `--target` to restrict the rebuild to one
   target. Unknown targets and disabled targets are rejected.
10. **Active-only retrieval.** Only active targets contribute hits, scores,
    hydration, status, and `stores_*` labels (`<target>:<strategy>`). A failed
    active strategy is recorded as failed and degrades the receipt to
    `PARTIAL`, or `FAILED` when the target is required. Shadow targets are
    queried only when shadow measurement is enabled and are reported only in
    `projection_evidence`, with zero contribution.
11. **facts-v8.** `config/projections/facts-v8.yaml` declares Graphiti
    `active` and Zep `shadow`, neither required.
12. **Schema 8.** SQLite and PostgreSQL migrate `projection_links` from
    `(record_id, projection_name)` to `(record_id, target_identity)`. Each
    existing row keeps its locator and link JSON, gains its projection name as
    its target identity and `legacy` as its provider type, and the migration
    verifies the row count before it commits.

## Alternatives Considered

- A composite adapter that fans out to Graphiti and Zep behind one adapter.
- Keeping one link per record and storing per-provider locators inside it.
- Inferring manifest mode from the presence of a manifest file.
- Running shadow retrieval on every search.

## Rejected Alternatives

- **Composite adapter.** It hides which provider failed, forces all targets to
  succeed or fail together, and cannot retire or erase one target alone.
- **One link with many locators.** A partial failure would have to rewrite a
  shared row, and deletion could not prove which copies remain.
- **Implicit manifest mode.** A file appearing on disk would change where data
  is sent. Runtime selection is a configuration decision.
- **Always-on shadow retrieval.** It adds provider latency and failure surface
  to every search for a target that must not change any result.

## Invariants

- MemoryService remains the canonical control plane; the runtime has no store
  access and the worker writes only through the record-store port.
- Every provider copy has its own link and its own outbox intent.
- A shadow or disabled target never changes returned hits, scores, hydration,
  receipt status, or `stores_*`.
- Deletion completes only when no projection link remains for the record.
- Legacy runtimes keep their identities; schema-7 links stay resolvable.
- No credentials are added to manifests or generated configuration.

## Consequences

- Graphiti can serve while Zep is filled and measured in shadow, then promoted
  by changing one manifest mode.
- Deletion and rebuild receipts are larger: they list every target.
- An operator can rebuild or drain one target without touching another.
- Only the `primary` target of each provider type can be credentialed until
  per-target credential binding is designed.

## Security Impact

Caller identity, authorization, consent, and phase-lock behavior are
unchanged. Deletion is stricter: a record cannot reach `DELETED` while any
target, including a disabled one, still holds a copy. Credentials stay in the
existing settings and secret sources; the manifest names targets only.

## Migration Impact

Schema version 8 for SQLite and PostgreSQL. The migration is in place, runs
once inside the initialization transaction, and is idempotent. PostgreSQL takes
an `ACCESS EXCLUSIVE` lock on `projection_links` and re-inspects it so
concurrent initializers cannot both migrate. Existing deployments stay on the
legacy runtime until `L9_MEMORY_PROJECTION_RUNTIME=manifest` is set. Drain the
outbox before switching a deployment to a multi-target runtime: events written
before this ADR carry no target identity and fail closed when more than one
target exists.

Links written by a legacy runtime keep the adapter name as their identity, and
both legacy backends name their adapter `graphiti`, so the link does not say
which provider holds the copy. The manifest runtime therefore does not adopt
them: their retire and erase events fail closed and retry, and a deletion of
such a record stays `DELETION_PENDING` until a legacy runtime erases the copy.
A clean cutover requires a store with no legacy links. Adopting legacy links
into a named manifest target is a follow-up decision, not part of this ADR.

## Validation Requirements

- `tests/unit/test_projection_runtime.py`: modes, compiler determinism,
  status binding, runtime partitioning, factory construction, fail-closed
  configuration, and legacy compatibility.
- `tests/integration/test_projection_targets.py`, against the in-memory,
  SQLite, and PostgreSQL stores: per-target links, independent delivery,
  retirement, reactivation, stale events, shadow isolation, active retrieval,
  partial retrieval failure, complete and partial deletion, disabled-target
  deletion, and targeted rebuild.
- `tests/integration/test_projection_link_migration.py`: schema-7 links
  migrate in place on SQLite and PostgreSQL and remain erasable.
- `bash scripts/validate_release.sh`.

## Rollback Conditions

Roll back if a manifest runtime loses a link, completes a deletion with a
remaining copy, or lets a shadow target change a search result. The preferred
rollback keeps the manifest runtime and sets the failing target to `disabled`:
its links stay erasable and nothing new is delivered there. Returning to the
legacy runtime is safe only when no manifest-identity links remain; otherwise
their erase events cannot resolve and those deletions stay pending and visible
rather than completing. Reverting the code to a pre-ADR-084 release is not a
configuration change: that code cannot write the schema-8 table, whose
`target_identity` column is required and whose key no longer includes
`projection_name` alone, so the table must first be restored from a pre-upgrade
backup or rekeyed back by hand.

## Supersedes / Superseded By

Extends ADR-063 (projection manifest compiler), ADR-057 (verified deletion),
ADR-074 (projection retirement lifecycle), and ADR-054 (strategy receipts).
Supersedes none. Superseded by none.
