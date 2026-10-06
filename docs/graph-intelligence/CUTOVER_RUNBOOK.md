<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/graph-intelligence/CUTOVER_RUNBOOK.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->

# Graph Intelligence Cutover Runbook (GI-090)

Decisions: [ADR-085](../adr/ADR-085-tenant-safe-graph-scope-key.md) (scope key and
rebuild), [ADR-092](../adr/ADR-092-graph-campaign-audit-remediation.md) (legacy erasure
obligations), [ADR-093](../adr/ADR-093-graph-intelligence-v1-closure.md) (cutover
receipt, rollback window, release gate).

**Audience:** the downstream executing agent (Cursor, under L9 governance) and
the operator who approves its protected steps. Execute the phases in order. Do
not skip a phase, do not reorder phases, and do not improvise past a STOP. Each
phase ends with evidence you must capture before starting the next.

## What this achieves

It moves a deployment's Graphiti projection to a fresh Neo4j 5.26 + GDS 2.13
database under GraphScopeKey v1 and turns on graph intelligence. The cutover
leaves two durable records in the canonical operation ledger:

1. **A graph cutover receipt**, written by `l9-memory record-graph-cutover`. It
   says when the new binding took over, what it replaced, and when the rollback
   window ends.
2. **A legacy release receipt**, written by `l9-memory
   release-legacy-projection` after the window. It says the previous store was
   destroyed. The release is refused before a cutover receipt exists and while
   its rollback window is open.

Canonical memory (`MemoryService` / `RecordStore`) is never migrated or rolled
back. Only the projection binding moves.

## Hard rules (STOP conditions)

Stop and report to the operator if any of these would be violated. Do not
work around them.

1. **Secrets.** Never paste, print, echo or commit a credential. Bind vault
   names from Infisical (`l9-aws-secrets`, `capability_bind`) or use the
   deployment's secret manager. Bindings in receipts are opaque references,
   never credentials.
2. **Protected infrastructure.** Docker, compose, `deploy/` and C1 files, and
   bringing a database up or down, need the operator's explicit approval
   (`APPROVED`) at the step that needs it (governance rules 90 and 93). Show
   the exact change first.
3. **Never destroy the previous database** before Phase 7's cutover receipt
   exists **and** its rollback window has ended.
4. **Never run `release-legacy-projection --apply`** until the previous
   database is actually destroyed. The release is the assertion that no legacy
   copy remains.
5. **After a rollback (Phase 8R), never release** until a new cutover has been
   recorded and its own window has ended. The code gate cannot know a rollback
   happened; this rule is yours.
6. **No raw Cypher writes** against the graph from this runbook. Graphiti is the
   only graph writer. The graph-intelligence reader is read-only.
7. **A failing check is a STOP**, not a retry loop. Report the command, its
   output (with secrets redacted) and your diagnosis.

## Inputs (the operator provides these before Phase 0)

| Name | Example | Meaning |
|---|---|---|
| `CHANGE_REF` | `CHG-2026-0412` | change or ticket reference; used on every receipt |
| `NAMESPACES` | `repo-a repo-b` | every namespace whose projection moves |
| `PREVIOUS_BINDING` | `neo4j://graph-host/graphiti` | opaque name of the store being retired |
| `NEW_BINDING` | `neo4j://graph-host/graphiti-v1` | opaque name of the fresh store |
| `ROLLBACK_WINDOW_HOURS` | `168` | how long the previous store is kept (operator policy; 168 = 7 days) |
| `EVIDENCE_DIR` | `.l9/cutover/$CHANGE_REF` | where you write receipts (never committed) |

Credentials, by vault name only (Infisical project Cursor-Governance, or the
deployment's secret owner):

| Vault name | Used by |
|---|---|
| `GRAPHITI_MCP_TOKEN` | l9-memory → Graphiti MCP server |
| Graphiti's Neo4j **writer** credential | the Graphiti deployment only |
| `L9_MEMORY_GRAPH_NEO4J_PASSWORD` (a separate **reader** credential) | l9-memory graph intelligence |
| `OPENAI_API_KEY` | Graphiti extraction, embeddings and reranking |

Operator CLI context for every `l9-memory` command below:

```bash
export L9_MEMORY_LOCAL_IS_ADMIN=true          # cutover and release require ADMIN
export L9_MEMORY_PROJECTION_BACKEND=http
mkdir -p "$EVIDENCE_DIR"
```

## Phase 0: Preconditions

1. The campaign PRs are merged to `main` (`l9-memory-graph-intelligence-v1`,
   PR-A … PR-J), and the deployment runs a release built from that `main`.
   Record `l9-memory --version` and the git SHA.
2. CI is green on that SHA, including the `graph-live` job. The latest
   `Graph qualification` workflow run is green.
3. **Back up the canonical store** by the deployment's standard procedure.
   Record the backup identifier. **STOP** if there is no verified backup.
4. `l9-memory health > "$EVIDENCE_DIR/00-health.json"`. The canonical store
   must be healthy.

## Phase 1: Bring up the fresh graph (protected, needs `APPROVED`)

Ask the operator for approval, showing the exact change. Then:

1. A fresh Neo4j **5.26.31** database with the GDS plugin: image `neo4j:5.26.31`
   installs **GDS 2.13.13**. Settings:
   `dbms.security.procedures.unrestricted=gds.*` and
   `dbms.security.procedures.allowlist=gds.*`.
2. A Graphiti **0.30.2** MCP server bound to that database, with Graphiti's
   writer credential and its model configuration:
   - `MODEL_NAME=gpt-5.5`
   - `SMALL_MODEL_NAME=gpt-4.1-nano`
   - embedder `text-embedding-3-large` at **3072** dimensions (the projection
     manifest `config/projections/facts-v8.yaml`)
   - `OPENAI_API_KEY` from the vault
3. Create the graph-intelligence **reader** user:
   - **Enterprise:** use the grants in [NEO4J_BINDING.md](NEO4J_BINDING.md)
     (MATCH plus GDS procedures; no write).
   - **Community:** there is no role-based access control. Use a credential
     distinct from Graphiti's. The adapter's read-only sessions and static
     templates are then the write barrier. Record in the evidence that the
     edition is Community.
4. Keep the previous database running and untouched.

Evidence: the image tags, the edition, and the operator approval.

## Phase 2: Bind l9-memory to the fresh graph

Set (secret values from the vault, never inline):

```bash
export GRAPHITI_MCP_URL=<fresh Graphiti MCP URL>
export L9_MEMORY_GRAPH_BACKEND=neo4j
export L9_MEMORY_GRAPH_NEO4J_URI=<bolt URI of the fresh database>
export L9_MEMORY_GRAPH_NEO4J_DATABASE=<database name>
export L9_MEMORY_GRAPH_NEO4J_USER=<reader user>
# L9_MEMORY_GRAPH_NEO4J_PASSWORD: bound from the vault by the deployment
export L9_MEMORY_GRAPH_REQUIRED=false          # enabled in Phase 9, not now
```

Deploy with these settings. Leave `L9_MEMORY_GRAPH_SCHEMA_FINGERPRINT` unset
until Phase 5.

## Phase 3: Rebuild the projection (per namespace)

For each namespace in `$NAMESPACES`:

```bash
l9-memory rebuild-projection --group-id "$NS" --limit 1000 > "$EVIDENCE_DIR/10-rebuild-$NS-preview.json"
l9-memory rebuild-projection --group-id "$NS" --limit 1000 --apply > "$EVIDENCE_DIR/11-rebuild-$NS-apply.json"
```

Repeat until a preview queues nothing (`queued_record_ids` empty). Then drain
the outbox: repeat `l9-memory outbox-run` until it reports `"claimed": 0`, and
confirm `outbox_backlog` is 0 in `l9-memory health`.

Each re-projected link records the copy left in the previous database as a
legacy erasure obligation (ADR-092). This is expected: those copies are
released in Phase 10.

**STOP** if any outbox event goes `dead`. Report it; do not force it.

## Phase 4: Warm analytics

The first GDS call on a freshly started server compiles its code paths and can
exceed the 3 s default request budget. Run one centrality, community and
structural-embedding operation per namespace once, through the MCP tools
`memory.graph.centrality`, `memory.graph.community` and
`memory.graph.structural_embedding`. Use `limits.max_runtime_ms: 30000`. A
FAILED `runtime_budget_exceeded` here is the cold start. Repeat once; a second
failure is a STOP.

## Phase 5: Verify

1. Call `memory.graph.capabilities` (MCP) and save it to
   `$EVIDENCE_DIR/20-capabilities.json`. Required:
   - `backend.reachable` and `backend.healthy` are true;
   - `schema_compatible` is true;
   - `scope_scheme_conformant` is true;
   - `analytics_available` is true;
   - `gds_catalog_active` is 0;
   - `projection_lag_events` is 0.
2. Record `backend.schema_fingerprint`. Set
   `L9_MEMORY_GRAPH_SCHEMA_FINGERPRINT=<that value>` and redeploy. From now on,
   readiness fails closed if the binding drifts.
3. Run the tenant-isolation suite against this configuration:
   `pytest tests/security/test_graph_tenant_isolation.py`.
4. Run the smoke checks per namespace, each on a known record or entity:
   - `memory.graph.search` with `anchor.query` returns `entity_hit` results
     with `supporting_record_ids`;
   - `memory.graph.neighborhood` with `anchor.record_id` is COMPLETE;
   - `memory.graph.semantic_search` returns its record.

Evidence: every response, saved under `$EVIDENCE_DIR/2*`.

## Phase 6: Tune against the real graph

The shipped ceilings were proven on fixture graphs. Tune them now, on the real
graph, before callers depend on it.

1. For each operation, over 20+ representative anchors per namespace, record
   p50/p95 latency (`memory_graph_query_latency_ms`), result sizes, and
   PARTIAL/`truncated` rates.
2. For GDS, read `scope_nodes` and `scope_relationships` from receipts. Compare
   them against `L9_MEMORY_GRAPH_GDS_MAX_NODES` (default 50000).
3. Set with at least 2× headroom over observed p95, or report that the graph
   needs a larger backend:
   - `L9_MEMORY_GRAPH_QUERY_TIMEOUT_MS`
   - `L9_MEMORY_GRAPH_GDS_MAX_NODES`
   - the request `max_runtime_ms` ceiling
4. Save the measurements and chosen values to `$EVIDENCE_DIR/30-tuning.json`.

Repeat this phase after the graph grows about 10×.

## Phase 7: Record the cutover receipt and rollback window

For each namespace, readiness check first, then record:

```bash
l9-memory record-graph-cutover --group-id "$NS" \
  --previous-binding "$PREVIOUS_BINDING" --new-binding "$NEW_BINDING" \
  --change-reference "$CHANGE_REF" --rollback-window-hours "$ROLLBACK_WINDOW_HOURS" \
  > "$EVIDENCE_DIR/40-cutover-$NS-check.json"
l9-memory record-graph-cutover --group-id "$NS" \
  --previous-binding "$PREVIOUS_BINDING" --new-binding "$NEW_BINDING" \
  --change-reference "$CHANGE_REF" --rollback-window-hours "$ROLLBACK_WINDOW_HOURS" \
  --apply > "$EVIDENCE_DIR/41-cutover-$NS.json"
l9-memory graph-cutover-status --group-id "$NS" > "$EVIDENCE_DIR/42-cutover-$NS-status.json"
```

The readiness check must show `"ready": true`, an empty
`unprojected_record_ids`, and `"outbox_backlog": 0`. `--apply` refuses
otherwise (`CutoverNotReady`); go back to Phase 3. The recorded receipt also
carries the live `schema_fingerprint` and served `graph_capabilities`.

Record `rollback_window_ends_at` for the operator. That is the earliest moment
Phase 10 may start.

Cutovers are tenant-scoped: record and read them as an ADMIN principal of the
tenant whose namespace migrated. A receipt covers only this migration. If the
namespace is migrated again later, record a new cutover for that migration;
the earlier receipt does not authorize releasing the newer legacy copies.

## Phase 8: Rollback window (monitor)

Until `rollback_window_ends_at`:

- Keep the previous database running and untouched.
- Watch:
  - `memory_graph_query_total{status="FAILED"}`;
  - `memory_graph_provider_failure_total`;
  - `memory_graph_partial_receipt_total`;
  - `gds_catalog_active` (it must return to 0);
  - `projection_lag_events`;
  - `rehydration_success_rate`.
- A verified deletion during the window erases the new copy and stays
  `deletion_pending`, because the previous database still holds one. This is
  expected.

### Phase 8R: Rollback (only if the operator orders it)

Rollback restores the previous projection binding; canonical memory is not
rolled back.

1. Set `GRAPHITI_MCP_URL` and the `L9_MEMORY_GRAPH_*` settings back to the
   previous binding (or `L9_MEMORY_GRAPH_BACKEND=none`), and redeploy.
2. Do **not** destroy either database. Do **not** run
   `release-legacy-projection` (hard rule 5).
3. Record the rollback in `$EVIDENCE_DIR/50-rollback.md`: the time, the reason,
   and the settings restored. A later attempt starts again from Phase 1 and
   records a new cutover receipt; the latest receipt governs.

## Phase 9: Enable callers

When the operator confirms (usually after the window), set
`L9_MEMORY_GRAPH_REQUIRED=true` if graph readiness should gate `/readyz`, and
redeploy. `memory.graph.capabilities` must report `ready: true`.

## Phase 10: Destroy the previous database, then release (protected, needs `APPROVED`)

Only after `rollback_window_ends_at`, and only if there was no rollback (or a
newer cutover's window has also ended):

1. `l9-memory graph-cutover-status --group-id "$NS"` must show
   `"legacy_release_open": true` for every namespace.
2. With the operator's approval, destroy the previous database. Record the
   destruction change reference as `DESTRUCTION_REF`.
3. For each namespace, preview then apply:

   ```bash
   l9-memory release-legacy-projection --group-id "$NS" \
     --store-destruction-reference "$DESTRUCTION_REF" > "$EVIDENCE_DIR/60-release-$NS-preview.json"
   l9-memory release-legacy-projection --group-id "$NS" \
     --store-destruction-reference "$DESTRUCTION_REF" --apply > "$EVIDENCE_DIR/61-release-$NS.json"
   ```

   The applied receipt carries `cutover_receipt_id`, the Phase 7 receipt.
   STOP if `--apply` refuses with "superseded after the latest recorded
   cutover": a later migration happened since Phase 7. Record its cutover
   (Phase 7) and wait for that window before releasing.
   Deletions that were waiting on legacy copies complete
   (`completed_deletion_record_ids`).
4. Check that running the preview again releases nothing.

## Final report (to the operator)

Report:

- `CHANGE_REF`
- the SHAs
- the backup identifier
- the edition
- per namespace:
  - records rebuilt
  - the cutover `receipt_id`
  - `rollback_window_ends_at`
  - the release `receipt_id`
  - completed deletions
- the tuning values chosen
- anything that STOPped and how it was resolved

Attach `$EVIDENCE_DIR`. Never include a credential.
