# ADR-075: Scheduled Canonical Memory Maintenance

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-075-scheduled-canonical-memory-maintenance.md
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

ADR-071 moved semantic deduplication off the write path. Admission answers
"is this a retry of a known operation?", which it can answer, and no longer
guesses at "does this mean the same thing as something we already know?",
which it cannot: that question needs temporal validity, contradiction, and
corroborating evidence that are not available while a single write is in
flight.

The consequence is that a namespace accumulates raw records — repeated
observations, differently worded agreement, facts the world has since changed.
Something has to resolve that later, with the whole namespace in view.

Doing it in a background thread inside the writing process was rejected early:
it would make consolidation depend on which agent happened to be running, and
give every writer's credentials the authority to rewrite shared memory.

## Decision

Maintenance is a scheduled pass over records that are already canonical,
performed under its own least-privilege authority.

**Authority.** `AuthorizationAction.MAINTAIN` with per-namespace grants. A
maintainer can consolidate, supersede, and archive. It cannot ingest, promote,
delete, or administer. `MemoryService.write` and the maintenance path share one
admission implementation behind an explicit authority gate, so derived records
pass the same normalization, consent, and admission law as any other write
while requiring a different grant.

**No ingestion surface.** `MaintenanceRequest` names a namespace, a bounded set
of operations, and limits. It forbids unknown fields and declares no field able
to carry content, a transcript, or a document, so a scheduled run cannot become
a back door for source ingestion.

**Planning is pure.** `MaintenancePlanner` takes records and returns actions.
It performs no I/O and mutates nothing, so a plan is reproducible and reviewable
before it is applied.

**Five bounded operations.**

- *dedupe* consolidates records whose normalized content is byte-identical, that
  share a memory class, and whose validity intervals overlap.
- *refine* consolidates differently worded records asserting the same subject,
  predicate, and object — corroboration that dedupe cannot see.
- *supersede* closes out a fact a later observation replaced: same subject and
  predicate, different object, strictly later validity.
- *archive* applies the existing retention policy to expired, unreferenced
  records.
- *reconcile* reports contradictions and changes nothing.

**Consolidation is additive.** A consolidation writes a new derived record that
cites its sources as both `references` and `supersedes`, carries the union of
their evidence plus an aggregation reference, and records the source ids in its
metadata. The sources become `SUPERSEDED`; their content, evidence, and history
are untouched. No canonical record is ever rewritten in place.

**Temporal safety.** Identical content over disjoint validity is not collapsed:
a fact that lapsed and returned keeps its gap. A changed fact is superseded, not
merged, so the history of what was true when survives. A genuine contradiction —
different objects over the same validity, where no ordering makes one the
successor — is reported for governance and left alone. Reconcile findings are
deliberately never marked applied, so they record no digest and resurface on
every run until someone resolves them.

**Idempotency and watermarks.** Each action carries an `action_digest` derived
from its operation and its exact source set. Applied digests are recorded in the
run ledger and skipped on later runs, and each derived record uses its action
digest as its idempotency key, so even a lost ledger makes a replay a duplicate
rather than a second record. A run considers only records with
`recorded_at <= watermark`, defaulting to the run's start, so writes landing
mid-run are out of scope rather than half-processed. Only applied runs advance
the watermark, so a dry run cannot cause the next real run to skip work.

Each record is consumed by at most one operation per run, so a single pass never
supersedes the same record twice.

## Alternatives Considered

- Keep semantic deduplication on the write path
- Run maintenance in a background thread inside each writing process
- Let maintenance rewrite records in place instead of deriving new ones
- Resolve contradictions automatically by preferring the newest or most
  confident record
- A scheduled pass under its own authority producing derived records

## Rejected Alternatives

- On-path deduplication is the defect ADR-071 removed: it discards corroborating
  observations and cannot see temporal evolution.
- An in-process background thread makes shared memory depend on which agent is
  running and hands every writer's credentials the authority to rewrite it.
- In-place rewriting destroys the bi-temporal history the store exists to keep,
  and would make lineage replay lie about what was known when.
- Automatic contradiction resolution guesses. "Newest wins" silently discards a
  correct record contradicted by a wrong newer one, and confidence scores are
  not comparable across sources.

## Invariants

- Maintenance requires MAINTAIN; it never requires or grants WRITE or ADMIN
- The request contract cannot carry raw source material
- Planning is pure and deterministic
- Consolidation derives a new record and supersedes its sources; nothing is
  rewritten in place
- Identical content over disjoint validity is never collapsed
- Contradictions are reported, never auto-resolved, and never suppressed
- A rerun over unchanged state performs no further actions
- Records recorded after the watermark are out of scope
- Only applied runs advance the watermark

## Consequences

Positive: Duplication is resolved with the whole namespace and its temporal
structure in view. The write path stays fast and honest. Every consolidation is
auditable: the derived record names its sources and the run ledger names the
action that produced it.

Negative: A namespace holds more raw records between runs. Consolidation
increases record count before it reduces retrievable duplication, since sources
are superseded rather than removed. Maintenance is another scheduled component
to operate and monitor.

## Security Impact

The nightly credential is least-privilege by construction: MAINTAIN over named
namespaces, with no ability to ingest, delete, or administer. Derived records
pass the same PII redaction, consent, and admission checks as any write, so
consolidation cannot launder content past admission policy.

## Migration Impact

No data migration. Existing namespaces are unchanged until a maintenance run is
invoked, and the first run is expected to consolidate a backlog. Operators
should run `l9-memory maintain` without `--apply` first and review the plan.

## Validation Requirements

- Tests prove consolidation produces a derived record citing its sources, with
  aggregated evidence, while sources remain intact as SUPERSEDED
- Tests prove maintenance succeeds under MAINTAIN with no WRITE grant, and is
  refused without MAINTAIN
- Tests prove disjoint validity is not collapsed
- Tests prove temporal evolution supersedes rather than merges
- Tests prove contradictions are reported, change nothing, and recur until
  resolved
- Tests prove a rerun is a no-op and that writes after the watermark are out of
  scope
- Tests prove a dry run changes nothing and does not advance the watermark
- All of the above run on the memory, sqlite, and postgres backends

## Rollback Conditions

Stop invoking maintenance. Records already consolidated stay consolidated;
their sources remain intact as `SUPERSEDED` and can be restored to `ACTIVE` by
an explicit governance action if a consolidation is judged wrong.

## Supersedes / Superseded By

Completes ADR-071 by giving the deferred semantic work a home. Extends ADR-008
supersession and the ADR-030 retention model.

No later ADR supersedes this decision as of 2026-08-20.
