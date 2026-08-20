# ADR-076: Projection Retirement Capability Ceiling

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-076-projection-retirement-capability-ceiling.md
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

ADR-074 separated projection retirement from privacy erasure. Retirement means
the canonical record is no longer current and its derivation must stop
surfacing it; erasure means the content must cease to exist. The two differ in
authority, in the receipts they produce, and in what survives.

They do not differ in the provider call. Graphiti exposes `delete_episode` and
no deactivation primitive, so `GraphitiProjection.retire` and
`GraphitiProjection.erase` both remove the episode. ADR-074 stated this, but
stating it left two costs unaddressed.

**Retirement was irreversible.** Withdrawing a projection removed the episode
and deleted the projection link, and nothing in the system could put it back.
If governance reversed an archive decision, the record returned to `ACTIVE` in
canonical state while remaining invisible to every projection-backed search.
There was no re-projection path at all, so "rebuildable from canonical state"
was true in principle and unreachable in practice.

**Retirement was not auditable from the provider.** Graphiti's own log shows
`delete_episode` for both operations. An auditor asking "was this episode
removed because the record was superseded, or because someone exercised a
right to erasure?" could not answer it from the provider. Canonical state did
distinguish the two — erasure leaves a `DeletionReceipt`, a tombstone, and
redacted content — but only by inference from an absence, and the retirement
itself left no durable record of what was withdrawn or when.

Neither cost is a defect in the sense of producing a wrong result. Both are
consequences of a provider ceiling, and both are fixable above the adapter.

## Decision

The ceiling is declared, retirement is recorded, and withdrawal is reversible.

**Declared.** `ProjectionAdapter.retirement_mode` is `RetirementMode.NATIVE`
when the provider can deactivate a projected record while keeping it, and
`RetirementMode.WITHDRAW` when the provider offers only removal. Graphiti is
`WITHDRAW`; `NullProjection` is `NATIVE` because nothing is projected. The
ceiling is machine-readable rather than prose, so a caller can tell whether
retirement is reversible at the provider, and a provider that later ships a
deactivation primitive changes one declaration.

**Recorded.** Retiring a projection writes a `ProjectionRetirementReceipt` to
canonical state: the record, namespace, provider, retirement mode, the locator
that was withdrawn, the reason, the originating outbox event, and the provider
result. `erasure` is a field on that receipt and is validated to be false, so a
retirement receipt cannot be made to assert erasure semantics. The audit
question is now answered from canonical state without consulting the provider.

**Reversible.** `MemoryService.rebuild_projection` re-projects every active
canonical record that has no live projection link, exposed as
`l9-memory rebuild-projection`. It requires `MAINTAIN` to apply and `READ` to
plan, defaults to a dry run, and never touches canonical state — projections
are derivations, so rebuilding is always safe. Withdrawal is therefore a
recoverable operation rather than a permanent one.

## Alternatives Considered

- Leave the ceiling documented in prose and accept both costs
- Refuse to retire on providers without a native deactivation primitive
- Emulate deactivation by re-projecting the record with an inactive marker
- Declare the ceiling, record the retirement, and add a rebuild path

## Rejected Alternatives

- Documenting the cost does not remove it. "Rebuildable in principle" with no
  rebuild path is a claim the system cannot honour.
- Refusing to retire would leave superseded and archived records serving stale
  truth from the projection, which is the defect ADR-074 exists to fix. A
  provider limitation must not become a correctness regression.
- An inactive marker depends on every provider supporting queryable status and
  every consumer filtering on it. Graphiti offers no such guarantee, so stale
  facts would still surface for anyone querying it directly.

## Invariants

- Every projection adapter declares a retirement mode
- Retiring a projection writes a retirement receipt to canonical state
- A retirement receipt can never assert erasure
- Privacy deletion produces a `DeletionReceipt` and no retirement receipt
- Rebuild re-projects only active records lacking a live projection link
- Rebuild never mutates canonical state
- Rebuild requires `MAINTAIN` to apply

## Consequences

Positive: A withdrawn projection is recoverable with one command. The
retirement/erasure distinction is answerable from canonical state alone. The
provider ceiling is explicit and testable rather than tribal knowledge.

Negative: Retirement now writes an extra receipt per withdrawn projection, so
a bulk retention run produces more receipt rows. Rebuild re-projects through
the normal outbox path, so a large rebuild generates provider traffic
proportional to the namespace and should be run deliberately rather than
routinely.

## Security Impact

The retirement receipt records a locator and a reason, not memory content. It
narrows an audit gap: previously the only evidence that a projected copy had
been withdrawn was the absence of a projection link. It remains not a privacy
control — only `erase` under a verified deletion receipt makes that claim, and
the receipt's `erasure` field is validated to keep the two from being confused.

## Migration Impact

No data migration. Retirements performed before this decision left no receipt
and are not backfilled; their evidence remains the absent projection link plus
the delivered retire outbox event. Existing deployments carrying projections
for records superseded or archived before ADR-074 can now withdraw them by
rebuilding, since rebuild projects only active records.

## Validation Requirements

- Tests prove each adapter declares its retirement mode
- Tests prove retirement writes a receipt naming the mode, locator, and reason
- Tests prove a retirement receipt cannot assert erasure
- Tests prove privacy deletion produces no retirement receipt
- Tests prove a withdrawn projection is restored by rebuild after the record
  returns to active
- Tests prove rebuild dry runs enqueue nothing, skip already-projected records,
  require `MAINTAIN`, and refuse when no projection is configured
- All of the above run on the memory, sqlite, and postgres backends

## Rollback Conditions

Reverting removes the rebuild path and restores irreversible withdrawal.
Receipts already written remain valid canonical evidence and are not removed.

## Supersedes / Superseded By

Completes ADR-074 by remediating the two costs it identified and accepted.
Extends ADR-025: projections remain rebuildable derivations, and this decision
supplies the mechanism that makes that property usable.

No later ADR supersedes this decision as of 2026-08-20.
