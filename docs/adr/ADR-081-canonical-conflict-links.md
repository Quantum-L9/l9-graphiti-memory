# ADR-081: Canonical Conflict Links

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-081-canonical-conflict-links.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-04
/L9_META -->


**Date:** 2026-09-04
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.3+

## Status

Accepted

## Context

`MemoryRecord.conflicts_with` existed from the first schema. Every store
persisted it, retention counted it as a reference that protects a record
from archive, and lineage replay traversed it as a parent edge. No producer
ever set it. Meanwhile `MemoryService.conflicts` recomputed every
contradiction in a namespace on each call, an O(n²) pass over structured
assertions, and both the phase-lock grant and the promotion check ran it on
every request. Scheduled reconciliation (ADR-075) found the same
contradictions again each night and reported them without recording them.

The forensic codebase audit of 2026-09-04 listed the unpopulated field as an
UNKNOWN. The operator chose to populate it.

## Decision

A conflict is a link that governed reconciliation writes onto both records.

**Writing.** `MemoryService.link_conflicts` under MAINTAIN validates that both
sides are active records of the tenant and namespace, drops pairs already
linked, and commits the rest through the new capability-gated
`RecordStore.commit_conflict_links` under a `ConflictLinkReceipt`. Every
adapter updates `conflicts_with` on both records and persists the receipt in
one transaction. The maintenance `RECONCILE` operation now applies by calling
it, and the planner skips pairs already linked, so a rerun is a no-op.

**Reading.** `MemoryService.conflicts` reports links between records that are
both still active. Reading the links is the whole cost, so a phase lock or a
promotion check no longer re-derives the namespace's contradictions. A link is
live only while both sides are active: superseding or archiving either side
resolves the conflict without anyone editing the link, and lineage keeps the
edge.

**Freshness.** The report is as current as the last reconciliation pass.
A contradiction written since then is not reported until maintenance runs
again. This is the trade the decision makes deliberately: the conflict report
guards governed writes and promotion against known, recorded contradictions,
and reconciliation is the single place contradictions are identified. An
operator who needs the report current before a governed write runs
`l9-memory maintain --operation reconcile` first.

## Alternatives Considered

- Keep recomputing overlaps on every report and ignore the field
- Compute links at write time, inside admission
- Remove the field and the branches that read it

## Rejected Alternatives

- Recomputation scales with the square of the namespace and had already made
  the field dead schema; it also gave governance nothing durable to act on.
- Admission answers "is this a retry?" and deliberately not "does this
  contradict something?" (ADR-071); moving contradiction detection into the
  write path would reintroduce the semantic guessing that ADR-075 moved out.
- Removing the field would discard the retention and lineage semantics that
  already consumed it correctly.

## Invariants

- `conflicts_with` is written only through `MemoryService.link_conflicts`, under a receipt
- Both sides of a link are active records of one tenant and namespace when linked
- A link is symmetric on both records
- The conflict report contains exactly the links whose both sides are active
- Reconciliation never resolves a conflict; only supersession or archive does
- A rerun of reconciliation over unchanged state writes nothing

## Consequences

Positive: contradictions become durable, evidenced, and cheap to consult;
phase locks and promotion stop paying for a namespace scan; retention's
protection of conflicting records finally has something to protect.

Negative: the report lags reconciliation, as stated above; a deployment that
never runs maintenance never sees a conflict, which the nightly workflow and
the maintenance receipts make visible.

## Security Impact

Linking is a canonical mutation and carries the service write capability like
every other one (ADR-036); the bypass scanner guards
`commit_conflict_links`. The receipt records who linked what and why. No new
authority is introduced: MAINTAIN could already supersede and archive.

## Migration Impact

No schema change; the column and JSON field existed. Existing namespaces
report no conflicts until their first reconciliation pass after this change,
which the nightly workflow performs. Existing tests that asserted an unlinked
contradiction was reported now run reconciliation first.

## Validation Requirements

- `tests/integration/test_conflict_links.py`, parameterized over
  `STORE_BACKENDS`: atomic symmetric linking under a receipt; the report reads
  links; phase lock and promotion refuse while linked; supersession resolves;
  reruns write nothing; the capability is required
- `tests/integration/test_memory_service.py::test_conflicts_deny_phase_lock`
  reconciles before asserting

## Rollback Conditions

Reverting restores the recomputing report; links already written stay on the
records as data the reverted report ignores, and lineage still traverses them.

## Supersedes / Superseded By

Narrows the conflict-report semantics of ADR-008 and ADR-075 to recorded
links; the phase-lock contract of ADR-079 is unchanged.

No later ADR supersedes this decision as of 2026-09-04.
