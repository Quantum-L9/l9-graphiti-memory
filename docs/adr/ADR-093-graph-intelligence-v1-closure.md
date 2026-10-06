# ADR-093: Graph Intelligence V1 Closure

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-093-graph-intelligence-v1-closure.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-09-27
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ (campaign `l9-memory-graph-intelligence-v1`, slice PR-J)

## Status

Accepted

## Context

A read against the graph-intelligence dev pack (v1.0.0) found the build nearly
complete but seven acceptance items open:

1. The GI-080 restart and outage cases were not tested.
2. `graph.search` answered COMPLETE and empty on real Graphiti, because
   entity-node hits carry no episode reference.
3. `profile_ref` was accepted and ignored, although algorithm profiles do not
   exist yet (a silent no-op, contrary to GI-032).
4. Three health dimensions from `10_OBSERVABILITY` were missing: active GDS
   catalog graphs, projection lag, and the rehydration success rate.
5. The live Neo4j/GDS suites skipped in CI; they had passed only on a
   developer machine.
6. Live qualification used a scripted LLM, hash embeddings and an overlap
   reranker.
7. There was no cutover receipt and no rollback window (GI-090), and nothing
   stopped a legacy release before cutover.

## Decision

1. **Outage and restart proof.** A live test stops and starts Neo4j under a
   running service. The commands come from `L9_MEMORY_TEST_NEO4J_STOP_CMD` and
   `L9_MEMORY_TEST_NEO4J_START_CMD`; CI supplies `docker stop/start` of its
   service container.
   - During the outage, health is a typed unreachable state and operations
     answer FAILED with a failure class, never empty COMPLETE.
   - Canonical memory keeps writing and searching (GI-031).
   - After the restart, the same service instance recovers and analytics
     recover. A fresh adapter binds the same graph with the same schema
     fingerprint.
   - Qualification adds a Graphiti process restart: a new Graphiti keeps the
     projection and keeps projecting.
   - The first GDS call on a freshly started server pays a cold-start cost that
     can exceed the 3 s default budget. The runbook warms analytics before
     callers are enabled.
2. **`graph.search` binds entity hits.**
   - `ProjectionAdapter.search_entities` keeps Graphiti entity hits that carry
     no record id.
   - `GraphIntelligencePort.describe_entities` binds them through the existing
     entity → `MENTIONS` → episode → record support path, scoped to the
     request's derived groups.
   - Binding is served where the baseline structural capabilities are.
   - Without such a backend, entity hits are reported as unsupported
     observations with a reason, never dropped.
   - Graphiti's ranking stays the source of `graph.search`. `memory.search` is
     unchanged (GI-036).
3. **`profile_ref` is refused** (`profile_not_supported`, stage `policy`) in
   shared request policy, before any operation-specific path, until profiles
   exist (dev-pack V1.2).
4. **Health dimensions.** The capability report adds:
   - `gds_catalog_active`, read from the database, so it survives restarts;
   - `projection_lag_events` (the outbox backlog);
   - `rehydration_success_rate`: admitted ÷ (admitted + dropped candidates),
     excluding candidates never attempted, such as those left unbound when no
     backend was available or the budget was spent.

   New gauges `memory_graph_gds_catalog_active` and
   `memory_graph_projection_lag_events`, and counter
   `memory_graph_rehydration_admitted_total`.
5. **CI.**
   - **`graph-live` in `ci.yml`, every PR.** The job:
     - runs a `neo4j:5.26.31` service, whose tag pins GDS 2.13.13;
     - waits for Bolt and GDS;
     - runs the four live suites, including outage and restart;
     - guards the set of live-bound files;
     - fails if any live test skips.
   - **`graph-qualification.yml`, nightly and on dispatch.** It runs the
     real-model qualification. It fails on a missing credential or a skip.
6. **Real models in qualification.** The stand-ins are deleted. The model stack
   comes from the GAR intelligence harvest (the settled Graphiti deployment and
   donor ADR-0029), with this repository's stronger semantics winning:
   - **LLM:** OpenAI `MODEL_NAME` (default `gpt-5.5`) and `SMALL_MODEL_NAME`
     (default `gpt-4.1-nano`). These are graphiti-core 0.30.2's own defaults.
     They replace the harvested `gpt-4o-mini`, which is outdated.
   - **Embedder:** the model and dimensions pinned by the projection manifest
     (`config/projections/facts-v8.yaml`: `text-embedding-3-large`, 3072).
     The harness reads the manifest; it does not keep a second copy.
   - **Reranker:** `OpenAIRerankerClient` on the small model.
   - **Route:** `L9_QUAL_MODEL_ROUTE` is `openai` (default, `OPENAI_API_KEY`)
     or `openrouter` (the same OpenAI models through OpenRouter's
     OpenAI-compatible API, `OPENROUTER_API_KEY`). The route is explicit and
     recorded, never a fallback.
   - Assertions are properties, because real extraction is not deterministic.
7. **Cutover receipt and rollback window.**
   - `MemoryService.record_graph_cutover` (CLI `record-graph-cutover`, ADMIN)
     writes an append-only `GraphCutoverReceipt` to the operation ledger. The
     write goes through the capability-gated `commit_graph_cutover`.
   - The receipt is written only when every ACTIVE record in the namespace has
     a live link under the current provider scope scheme and the outbox is
     drained.
   - It records:
     - the previous and new binding (opaque references, never credentials);
     - the change reference;
     - the schema fingerprint and served capabilities;
     - the rollback window end.
   - `release_legacy_projection_copies(apply=True)` refuses (`CutoverNotReady`)
     until a cutover is recorded and its rollback window has ended.
   - The release receipt names the cutover that authorized it.
   - The latest cutover governs; earlier ones are kept.
   - Cutovers are tenant-scoped. The receipt carries the recording principal's
     `tenant_id`, and a release consults only its own tenant's cutovers: one
     tenant's closed window never opens another tenant's release in a shared
     namespace.
   - A cutover covers only the migration it recorded. An applied release
     refuses while any legacy copy it would release was superseded after the
     latest cutover; a later migration (B → C) needs its own cutover and
     window before B's copies may be declared destroyed.
   - `graph-cutover-status` reports the window. It is ADMIN, like recording,
     because receipts name bindings and actors.
   - Operator procedure: `docs/graph-intelligence/CUTOVER_RUNBOOK.md`.
8. **Integration with the projection runtime (ADR-084).** The campaign
   (ADR-085…ADR-093, originally numbered 084…092) merged after `main` adopted
   target-aware projections. Its single-projection rules now apply per
   target:
   - **Graph target.** Graph intelligence follows exactly one projection
     target (`projections.runtime.graph_projection_target`): in legacy mode the
     scalar adapter's target; in manifest mode the single active target serving
     `graph-search`, else the single active target. Shadow and disabled targets
     never feed it, and more than one candidate fails startup rather than
     picking a graph. `graph.search`, semantic graph strategies and the cutover
     readiness check all use this target.
   - **Delivery placement.** Manifest delivery (`project_rendered`) is placed
     like scalar delivery: the tenant-scoped group (ADR-085) and the canonical
     episode name with no `uuid` argument (ADR-091). Both paths record the
     scope scheme on the link.
   - **Stale-scope rebuild.** Each delivering target whose adapter declares a
     scope scheme re-projects its own stale or withdrawn links;
     `stale_scope_record_ids` reports them across targets.
   - **Legacy obligations per target.** Legacy copies, the withdrawn flag and
     the pending deletion receipt live on each target's link. A release clears
     every link of a record that carries legacy copies, and completes the
     deletion only when that leaves the record with no link in any target.
     Otherwise the store's guard (ADR-084, "no completion while any link
     remains") keeps the deletion pending until the other targets' erase
     events succeed.
9. **Confirmed ingestion and readiness (review of #83).**
   - Cutover readiness counts a record as projected only when its link is
     live under the current scope scheme **and** the graph target's adapter
     lists its episode (`GraphitiProjection.confirmed_records`, bounded by
     the episode lookup limit). Graphiti's `add_memory` only queues
     ingestion and can drop it, so a link alone is not proof. A record
     outside the lookup window, or a failed listing, is unconfirmed and the
     cutover is refused.
   - `L9_MEMORY_GRAPHITI_EPISODE_LOOKUP_LIMIT` sets the bounded episode
     lookup for both legacy and manifest Graphiti targets.
   - A required graph backend must be enabled as well as healthy: the
     `none` backend no longer satisfies `L9_MEMORY_GRAPH_REQUIRED=true`.
   - Link prediction applies the valid-time and transaction-time filters to
     every relationship it reads (path edges, the existing-edge check and
     neighbour degree).
   - Retirement and erasure by name locator fail closed when the episode
     listing returns as many episodes as the lookup limit: a retried write
     can leave a duplicate outside a truncated window, so the visible matches
     do not prove the copy is gone (review of #84).
   - Equal-length shortest paths are ordered by their node and relationship
     uuid sequences before the path budget applies, so the kept paths and the
     receipt digest are deterministic (review of #84).

## Alternatives Considered

- Serving `graph.search` from Neo4j full-text search instead of Graphiti's
  hybrid node search.
- Dropping `graph.search` from the capability report.
- Running real-model qualification on every PR.
- Recording cutover in the runbook only, without a store record or a release
  gate.
- Keeping deterministic stand-ins next to the real models.

## Rejected Alternatives

- **Neo4j full-text for `graph.search`.** It would change what `graph.search`
  means (the dev pack defines it as Graphiti's graph search) and lose its
  ranking.
- **Dropping the capability.** It is less than the contract promises.
- **Real models per PR.** Every run spends tokens and is non-deterministic.
  The deterministic live suites gate PRs; the real-model run gates nightly.
- **Runbook-only cutover.** An instruction cannot stop a premature release.
  The release is the assertion that the previous store is gone, so the gate
  belongs where the assertion is made.
- **Stand-ins alongside real models.** An inactive stub is a path by which a
  green run proves nothing.

## Invariants

GI-018, GI-026, GI-027, GI-029, GI-031, GI-032, GI-036, GI-080, GI-090;
AGENTS.md invariants 3, 6 and 8.

## Consequences

- `graph.search` returns entity hits with canonical support on real Graphiti.
- A legacy release now needs a recorded cutover with a closed rollback window.
  An in-place migration without a cutover keeps its deletions pending until one
  is recorded.
- CI proves the live graph suites on every PR. Real-model qualification needs
  the model credential in the repository's Actions secrets.
- Graphiti restart, Neo4j restart and outage are exercised.

## Security Impact

- The cutover and release gate close a lifecycle gap: the previous store
  cannot be declared destroyed before the cutover is recorded or while the
  rollback window is open.
- `describe_entities` is scoped to the principal's derived groups. A foreign
  entity returned by a hostile provider is reported `entity_not_found` and
  never served.
- Model credentials come only from the environment or an in-process binding.

## Migration Impact

- No schema change. Cutover receipts use the existing `operation_receipts`
  table (kind `graph_cutover`).
- `LegacyProjectionReleaseReceipt.cutover_receipt_id` is optional and reads
  older receipts as `None`.
- Deployments must record a cutover before releasing legacy copies.
- Campaign ADRs were renumbered 084…092 → 085…093 when they merged over
  `main`'s ADR-084; content is unchanged.

## Validation Requirements

- `tests/unit/test_graph_search_entity_binding.py`: binding, foreign support,
  no-backend reporting, missing entity, binding failure, merge, `profile_ref`
  refusal, `search_entities` scoping.
- `tests/unit/test_graph_health_dimensions.py`.
- `tests/integration/test_neo4j_restart_outage_live.py`, plus the live
  `graph.search` binding test in `test_neo4j_graph_traversal.py`.
- `tests/security/test_graph_cutover.py` (memory, SQLite, PostgreSQL):
  readiness refusal, persistence across restart, capability gate, release
  refused before the receipt and within the window, the latest cutover
  governs, tenant scoping, a later migration needs its own cutover, ADMIN
  only for recording and status.
- `tests/integration/test_projection_targets.py` (memory, SQLite,
  PostgreSQL): the graph target is the one active graph target; legacy
  obligations are per target; a release completes a deletion only when no
  other target holds a copy.
- `tests/qualification`: 15 real-model cases.

## Rollback Conditions

Revert the slice. Recorded cutover receipts remain in the ledger and are
ignored by older code. `graph.search` returns to COMPLETE-empty for entity
hits.

## Supersedes / Superseded By

Amends ADR-084, ADR-085, ADR-087, ADR-090, ADR-091 and ADR-092. Superseded by none.
