# ADR-091: Graph Campaign Audit Remediation

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-091-graph-campaign-audit-remediation.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-09-26
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ (campaign `l9-memory-graph-intelligence-v1`, remediation slice PR-H)

## Status

Accepted

## Context

An independent audit of the campaign slices found four defects that CI did
not catch:

1. **Erasure hole during the GraphScopeKey migration (ADR-084).** The
   migration rebuilds into a fresh provider database and keeps the previous
   one for rollback. Re-projection overwrote the only projection link, so a
   verified deletion during the rollback window erased the new copy and
   reported COMPLETE while the previous database still held a copy.
2. **Paths served over unsupported relationships (ADR-086/087).** A path was
   admitted when every node had canonical support, even if the relationship
   between two nodes had none. Node support was then reported as the path's
   support.
3. **`max_runtime_ms` was not a request-wide budget.** Every Neo4j statement
   in an operation received the full budget, and graph and semantic search
   passed no budget to the projection.
4. **Search bypassed shared request policy.** `graph.search` and
   `graph.semantic_search` returned before the relationship allowlist check;
   an inadmissible algorithm raised instead of producing a FAILED receipt; and
   inapplicable fields were silently ignored.

## Decision

1. **Legacy erasure obligations.** When a projection link is replaced by one
   written under a different scope scheme, the superseded copy is recorded on
   the new link as a legacy copy (`legacy_copies`). A retirement keeps the
   link, marked withdrawn, while legacy copies remain. Verified erasure
   removes the reachable copy; if legacy copies remain, the record stays
   `DELETION_PENDING` and the link records the waiting deletion receipt.
   `MemoryService.release_legacy_projection_copies` (CLI
   `l9-memory release-legacy-projection --store-destruction-reference …`,
   ADMIN) is run after the retained store is destroyed. It clears the
   obligations and completes the waiting deletions. Rebuild treats a withdrawn
   link on an active record as unprojected.
2. **Path admission requires every relationship.** A path is served only when
   every node is supported, every hop has an identified edge, and every edge
   was admitted with canonical support. Its support is the union of node and
   edge support. Otherwise it is reported as unsupported
   (`unsupported_hop` or `unsupported_relationship`).
3. **One deadline per request.** `GraphIntelligenceService` fixes a monotonic
   deadline when an operation starts, clamped to the deployment ceiling.
   - The provider receives only the budget left, and none below 10 ms
     (`runtime_budget_exhausted`).
   - An answer that arrives after the deadline is refused
     (`runtime_budget_exceeded`).
   - The Neo4j adapter binds one deadline per operation. Each statement gets
     at most the remaining time, and none starts once the budget is spent
     (`GraphRuntimeBudgetExceeded`). GDS catalog cleanup still runs.
   - Search calls the projection once per namespace, checking the deadline
     between calls. A call that returns late is discarded. What completed in
     time is served as PARTIAL with `runtime_budget_exhausted`.
4. **Shared policy before the search split.** The relationship allowlist
   applies to every operation. Search resolves its algorithm inside the
   policy normalization (`algorithm_not_admitted`). It refuses `target`,
   `relationship_types` and a non-default `direction` with
   `request_field_not_applicable`.

## Alternatives Considered

- A second projection-link row per legacy copy.
- Erasing the legacy copy by reaching the retained database from the worker.
- Serving late answers and only reporting the overrun.
- Passing a timeout argument through the `ProjectionAdapter` port.

## Rejected Alternatives

- A second row changes the `(record_id, projection_name)` link key in every
  store backend. Link metadata carries the obligation without a schema change.
- Binding the worker to a database the deployment has deliberately cut over
  from reintroduces the old binding at runtime. The operator already owns its
  destruction (migration step 7).
- A ceiling that is only reported is not a ceiling.
- Changing the port touches every projection adapter. Per-namespace calls
  bound the request without it; a single in-flight call stays bounded by its
  transport's timeout.

## Invariants

GI-010, GI-026, GI-029, GI-031; AGENTS.md invariants 3 and 6 (atomic,
evidence-bearing canonical persistence; no bypass).

## Consequences

- Deletions during a migration rollback window complete only after the
  retained store is destroyed and released.
- Paths are fewer but always backed by evidence for every relationship.
- Requests end near `max_runtime_ms`. The time between the last check and a
  provider's reply is bounded by driver and transport timeouts.

## Security Impact

Closes a privacy-lifecycle gap: a COMPLETE deletion receipt no longer coexists
with a retained provider copy. Release requires ADMIN and a destruction
reference. Path evidence can no longer be borrowed from endpoints.

## Migration Impact

No store schema change. Links written before this change carry no
obligations; the obligation is recorded when the ADR-084 rebuild runs. Run
`release-legacy-projection` after migration step 7.

## Validation Requirements

- `tests/security/test_legacy_projection_erasure.py`: obligation recorded;
  deletion pending through the window; release completes it; retirement
  keeps the obligation; active records keep their link; ADMIN required; no
  change without legacy copies.
- `tests/unit/test_graph_evidence_linking.py`: unsupported relationship,
  unidentified hop, union support.
- `tests/unit/test_graph_request_budget_and_policy.py`: remaining budget to the
  provider, refusal when spent, late answer refused, adapter statements share
  one budget, GDS cleanup after exhaustion, search policy refusals, and a
  multi-namespace deadline yielding PARTIAL.

## Rollback Conditions

Revert the slice. Links carrying `legacy_copies` then behave as ordinary links.
Deletions waiting on them must be completed by releasing first.

## Supersedes / Superseded By

Amends ADR-084 (migration), ADR-086 (evidence, limits) and ADR-087 (paths,
search). Superseded by none.
