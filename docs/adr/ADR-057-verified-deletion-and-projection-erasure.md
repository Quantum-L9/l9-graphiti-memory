# ADR-057: Verified Deletion and Projection Erasure

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-057-verified-deletion-and-projection-erasure.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-04
/L9_META -->


**Date:** 2026-07-22
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.1+

## Status

Accepted

## Context

Archive and retention do not satisfy a verified deletion request. Canonical content and external projections can diverge, and pretending a provider erased content without a stable locator is unsafe.

## Decision

Administrative deletion requires a reason and verification reference. The canonical store immediately commits a redacted tombstone and deletion receipt. With no external projection, deletion completes. With a projection, the record enters deletion_pending and an erase outbox event must complete before the receipt becomes complete. Projection writes persist a stable provider locator in a canonical ProjectionLink. Graphiti erasure calls delete_episode with that locator; Zep erasure calls graph.episode.delete. Missing locators or unsupported deletion tools fail explicitly.

## Alternatives Considered

- Hard-delete without a receipt
- Treat archive as deletion
- Mark deletion complete before provider confirmation

## Rejected Alternatives

- Hard-delete erases audit evidence
- Archive preserves content
- Premature completion creates false privacy claims

## Invariants

- Only administrators can request deletion
- Canonical content is redacted and evidence/consent removed
- A tombstone preserves non-content audit identity
- Projection completion is evidence-backed
- Provider inability is reported, not hidden

## Consequences

Positive: Deletion state is inspectable and retryable

Negative: Live provider confirmation still requires disposable provider environments and credentials

## Security Impact

This is a privacy and security control. Tombstones minimize retained content while preventing silent re-ingestion and preserving accountability.

## Migration Impact

Legacy deletion requests require verification and become new receipts. Existing provider episodes must be inventoried before production cutover.

## Validation Requirements

- In-memory and SQLite deletion conformance
- Projection-link persistence and outbox erasure completion tests
- Graphiti and Zep deletion-adapter tests
- Non-admin denial tests
- Live provider deletion rehearsal before production

## Rollback Conditions

Restore the pre-deletion backup only under approved incident procedure; otherwise continue retrying pending projection erasure.

## Supersedes / Superseded By

Implements ADR-024 and extends ADR-018.

No later ADR supersedes this decision as of 2026-07-22.

## Amendments

**2026-09-04 — deletion is evidenced and not repeatable.**

The forensic codebase audit (findings F-11, F-13, F-03) found that deletion
changed a record's state twice, to `DELETION_PENDING` and then `DELETED`,
without appending either transition to the status-event ledger every other
transition writes to; that a record already deleted or pending deletion could
be deleted again, producing a second receipt and a second erase event; and
that an erase event for a record whose projection had already been withdrawn
dead-lettered instead of completing.

`commit_deletion` now takes the `ACTIVE → DELETION_PENDING` status event and
inserts it in the same transaction as the tombstone; `complete_deletion`
appends `DELETION_PENDING → DELETED` when the erase is confirmed, with the
worker's identity as actor. `MemoryService.delete` refuses a record already in
either deletion state with an `AdmissionError`. An erase event that finds no
projection link completes the deletion, as ADR-074 already ruled for
retirement.
