# ADR-057: Verified Deletion and Projection Erasure

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-057-verified-deletion-and-projection-erasure.md
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
