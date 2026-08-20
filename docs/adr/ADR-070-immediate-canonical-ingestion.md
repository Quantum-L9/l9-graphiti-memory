# ADR-070: Immediate Canonical Ingestion

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-070-immediate-canonical-ingestion.md
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

ADR-055 admitted a filesystem-backed ingress recovery queue so that a write
which could not reach the canonical store was preserved for later replay. In
practice this created a second, competing notion of what a successful memory
write means. A caller that received `status="queued"` had no canonical record,
no receipt, no admission decision, and no temporal coordinates, yet had been
told the operation succeeded. Downstream agents then read a namespace that
silently lacked memories they believed were written, and the divergence stayed
invisible until an operator ran a replay command by hand.

Availability was not actually improved. The queue converted a loud, local,
recoverable failure into a quiet, distributed, unbounded one.

## Decision

A memory write becomes canonical during the operation that requests it, or it
fails visibly. `MemoryService.write` remains the only admission path, and every
surface above it either returns a `WriteReceipt` describing a real canonical
outcome or raises.

`FileWriteRecoveryQueue` and the `recovery` package are removed. No runtime path
may serialize a `MemoryWriteRequest` to durable storage for later ingestion;
`tools/assurance/check_memory_write_bypass.py` enforces this structurally with a
`deferred-canonical-ingestion` rule.

Operators upgrading from a release that ran the queue keep a one-way drain,
`l9_graphite_memory.migration.LegacyWriteQueueDrain`, exposed as
`l9-memory drain-legacy-write-queue`. It reads pre-existing queue files, replays
them through `MemoryService`, and preserves anything it cannot parse or admit.
It has no enqueue method, so it can drain the retired state but never recreate
it.

Semantic duplication is admitted on the hot path and resolved later by scheduled
maintenance (ADR-075). Availability of the canonical store is a durability
concern, addressed by a shared backend (ADR-072), not by local queues.

## Alternatives Considered

- Keep the queue but rename the deferred outcome so it reads as a failure
- Retain the queue for hook and CLI surfaces only
- Replace the queue with an in-process retry loop around the store
- Remove deferred ingestion entirely and drain legacy state one way

## Rejected Alternatives

- Renaming the status leaves two durable sources of admitted-but-uncommitted
  intent, which is the defect itself rather than its presentation.
- A surface-scoped queue still means the same content is canonical for one
  caller and pending for another, so namespace state depends on ingress route.
- Bounded in-process retry is a store-adapter concern; hoisting it into the
  ingestion contract re-creates the deferred outcome under another name.

## Invariants

- A write call returns a canonical receipt or raises; there is no third outcome
- No production module persists a `MemoryWriteRequest` for later ingestion
- The legacy drain replays only through `MemoryService`
- The legacy drain never deletes a queued write it did not successfully admit
- Store failure propagates to the caller as `StoreError`

## Consequences

Positive: Namespace state is exactly what callers were told it is. Canonical
store outages become immediately visible instead of silently deferred.

Negative: Callers that previously received `status="queued"` must now handle a
raised exception. Store availability becomes a first-order operational
requirement rather than something local disk papers over.

## Security Impact

Removing the queue removes a filesystem location that held unredacted memory
content outside the canonical store's access controls. The legacy drain reads
that location only during migration and inherits state-directory permissions.

## Migration Impact

Operators who ran a release with the ingress queue must run
`l9-memory drain-legacy-write-queue` before removing the state directory. The
command exits non-zero while any pending item remains unreadable or
undeliverable, so queued writes are never dropped silently. A dry run is
available with `--dry-run`.

## Validation Requirements

- Fault injection proves a canonical-store failure raises rather than queues
- Structural scan proves no live enqueue path exists in the package
- Drain tests prove legacy items replay through `MemoryService`
- Drain tests prove unreadable and undeliverable items are preserved

## Rollback Conditions

Reverting requires restoring the `recovery` package and its callers. Any items
drained under this decision are already canonical and must not be replayed a
second time; their idempotency keys make a repeat drain a duplicate rather than
a new record.

## Supersedes / Superseded By

Supersedes ADR-055. Narrows ADR-018 to post-commit projection delivery only.

No later ADR supersedes this decision as of 2026-08-20.
