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
   A link still carrying another scope scheme when a retirement or erasure
   runs (the rebuild queued but not yet projected) is itself treated as a
   legacy copy. It is never erased through the new provider with a locator
   that addresses the retained store.
   `MemoryService.release_legacy_projection_copies` (CLI
   `l9-memory release-legacy-projection --store-destruction-reference …`,
   ADMIN) is run after the retained store is destroyed. It clears the
   obligations and completes the waiting deletions through one
   capability-gated store commit, `commit_legacy_projection_release`. That
   commit persists the receipt to the operation ledger, rewrites or removes the
   links, and completes the deletions in a single transaction. The commit
   also receives every link as it was read when the release was planned, and
   applies nothing if any has changed since. A concurrent outbox erasure can
   therefore never be overwritten by a stale plan, and the operator simply
   retries. In the in-memory store, link writers take the same lock the
   release holds, so a link write cannot land between the check and the
   apply. `list_legacy_projection_releases` reads the ledger. Rebuild
   treats a withdrawn link on an active record as unprojected.
2. **Path admission requires every relationship.** A path is served only when
   every node is supported, every hop has an identified edge, and every edge
   was admitted with canonical support. Each hop's edge must also connect
   exactly that hop's two nodes, in the request's orientation (`out`:
   node[i]→node[i+1]; `in`: the reverse; `both`: either). The path must be
   well formed: length+1 distinct nodes and distinct edges. Its support is the
   union of node and edge support. Otherwise it is reported as unsupported
   (`unsupported_hop`, `unsupported_relationship`,
   `relationship_does_not_connect_hop` or `malformed_path`).
3. **One deadline per request, and a hard ceiling on the caller's time.**
   `GraphIntelligenceService.execute` runs the whole operation on a bounded
   worker pool and waits at most `max_runtime_ms` (clamped to the deployment
   ceiling). That covers health probing, the provider, canonical evidence
   rehydration, GDS cleanup and projection transport alike. When the wait
   ends first, the caller gets FAILED `runtime_budget_exceeded` (stage
   `request`), built without touching the backend. The work still in flight
   ends against its own statement and transport timeouts, GDS catalog cleanup
   included, and its result is discarded. Both worker pools (whole operations
   and projection search calls) have bounded admission (workers plus an equal
   backlog). A request that finds the pool full is refused at once with
   `graph_capacity_exhausted` (stage `admission`), so a hung backend cannot
   make queued requests accumulate. Inside the operation the service also
   fixes a monotonic deadline:
   - The provider receives only the budget left, and none below 10 ms
     (`runtime_budget_exhausted`).
   - An answer that arrives after the deadline is refused
     (`runtime_budget_exceeded`).
   - The Neo4j adapter binds one deadline per operation. Each statement gets
     at most the remaining time, and none starts once the budget is spent
     (`GraphRuntimeBudgetExceeded`). GDS catalog cleanup still runs.
   - Search calls the projection once per namespace, on a bounded worker pool,
     and waits at most the remaining budget. A stalled call is abandoned at the
     deadline; it ends at its transport timeout and its result is discarded.
     What completed in time is served as PARTIAL with
     `runtime_budget_exhausted`.
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
- Changing the port touches every projection adapter. A worker-pool deadline
  bounds the request for any adapter; the abandoned call still holds a worker
  until its transport timeout.

## Invariants

GI-010, GI-026, GI-029, GI-031; AGENTS.md invariants 3 and 6 (atomic,
evidence-bearing canonical persistence; no bypass).

## Consequences

- Deletions during a migration rollback window complete only after the
  retained store is destroyed and released.
- Paths are fewer but always backed by evidence for every relationship.
- The caller never waits longer than `max_runtime_ms` plus scheduling slack.
  Abandoned work holds a pool worker until its own timeout. A saturated pool
  turns into immediate `graph_capacity_exhausted` refusals, never an
  unbounded queue.
- Deletions of records whose rebuild had not yet run also wait for the
  release. An in-place upgrade without the fresh-database rebuild (which
  ADR-084 forbids) keeps every such deletion pending until release.

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
  change without legacy copies; deletion or retirement before the rebuild
  runs; release atomic, persisted and capability-gated on memory, SQLite and
  PostgreSQL.
- `tests/unit/test_graph_evidence_linking.py`: unsupported relationship,
  unidentified hop, union support, a supported edge between other nodes
  (hostile), hop orientation per direction, malformed shapes, a matching
  two-hop path.
- `tests/security/test_legacy_projection_erasure.py` also covers injected
  failure mid-commit, process restart and idempotent retry, and a plan
  overtaken by a concurrent erasure, on memory, SQLite and PostgreSQL.
- `tests/unit/test_graph_request_budget_and_policy.py`: remaining budget to the
  provider, refusal when spent, late answer refused, adapter statements share
  one budget, GDS cleanup after exhaustion, search policy refusals, a
  multi-namespace deadline yielding PARTIAL, and a stalled provider abandoned
  at the deadline. Wall-clock bounds (150 ms budget, under 0.6 s total) hold
  for slow health, slow evidence rehydration, slow GDS cleanup (which still
  completes) and a stalled projection transport on both search strategies.

## Rollback Conditions

Revert the slice. Links carrying `legacy_copies` then behave as ordinary links.
Deletions waiting on them must be completed by releasing first.

## Supersedes / Superseded By

Amends ADR-084 (migration), ADR-086 (evidence, limits) and ADR-087 (paths,
search). Superseded by none.
