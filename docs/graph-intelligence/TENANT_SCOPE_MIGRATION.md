<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/graph-intelligence/TENANT_SCOPE_MIGRATION.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->

# Tenant-Safe Graph Scope Migration (GraphScopeKey v1)

Decision: [ADR-084](../adr/ADR-084-tenant-safe-graph-scope-key.md).
Campaign: `l9-memory-graph-intelligence-v1`, slice PR-A.

## What changes

| Surface | Before | After |
|---|---|---|
| Graphiti episode `group_id` | `record.namespace` | `l9g-v1-` + sha256(canonical_json({namespace, tenant_id})) |
| Graphiti search `group_ids` | `[namespace]` per authorized namespace | `[graph_group_id(principal.tenant_id, namespace)]` per authorized namespace |
| Projection payload | no scope binding | `scope_scheme`, `scope_digest` (never the raw tenant id) |
| Projection link metadata | transport result only | adds `scope_scheme` |
| `ProjectionAdapter.search*` | `(…, namespaces, *, limit)` | `(…, namespaces, *, limit, tenant_id)` |
| `rebuild-projection` | re-projects records without a live link | also re-projects records whose link has an older or missing `scope_scheme` (`stale_scope_record_ids`) |

Canonical records, record ids, episode UUIDs (= canonical `record_id`),
retirement, and erasure are unchanged. Retirement and erasure address episodes
by the persisted locator, so they work for copies written under either scheme.

## Behavior between deploy and rebuild

Canonical search is unaffected. Graph and semantic projection strategies query
only the new groups, so they return no hits for a namespace until its records
are re-projected. The receipt still reports the strategies as succeeded; this is
an empty projection, not a provider failure.

## Cutover

In-place group rename is forbidden. Re-projecting into the same Graphiti
database would move episodes but leave entities and edges already extracted
into the old namespace-keyed groups, so rebuild into a fresh database.

1. Back up the canonical store.
2. Provision a fresh Neo4j database and bind a Graphiti v0.30.2 instance to it.
3. Deploy this release pointing `GRAPHITI_MCP_URL` at the fresh Graphiti.
4. For each tenant/namespace, preview then apply:

   ```bash
   l9-memory rebuild-projection --group-id <namespace> --limit 1000
   l9-memory rebuild-projection --group-id <namespace> --limit 1000 --apply
   ```

   `queued_record_ids` lists every record to project; `stale_scope_record_ids`
   is the subset whose link predates GraphScopeKey v1. Repeat until a preview
   queues nothing. Drain the outbox.
5. Verify every projected episode maps back to exactly one canonical record and
   run `tests/security/test_graph_tenant_isolation.py` against the deployment's
   configuration.
6. Keep the previous Graphiti database for the rollback window. Each
   re-projected link records the copy left there as a legacy erasure
   obligation (ADR-091). A verified deletion during the window erases the
   new copy but stays `deletion_pending`, because the previous database
   still holds one.
7. Destroy the previous database only after cutover is verified. Then release
   the obligations, which completes the waiting deletions:

   ```bash
   l9-memory release-legacy-projection --group-id <namespace> \
     --store-destruction-reference <change-id>            # preview
   l9-memory release-legacy-projection --group-id <namespace> \
     --store-destruction-reference <change-id> --apply
   ```

   Never release before the database is destroyed: the release is the
   assertion that no legacy copy remains.

## Rollback

Restore the previous projection binding (`GRAPHITI_MCP_URL`) and the previous
release. Canonical memory is never rolled back; any graph written during the
window is rebuildable from canonical state.
