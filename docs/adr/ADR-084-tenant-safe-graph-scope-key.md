# ADR-084: Tenant-Safe Graph Scope Key

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-084-tenant-safe-graph-scope-key.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-09-25
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ (campaign `l9-memory-graph-intelligence-v1`, slice PR-A)

## Status

Accepted

## Context

Canonical memory identity is `tenant_id + namespace + record_id` (ADR-006,
ADR-025). The Graphiti projection did not carry that identity to the provider.
`GraphitiProjection.project` wrote every episode with `group_id=record.namespace`,
and `search_strategy` queried `group_ids=[namespace]`. Two tenants that use the
same namespace string therefore shared one provider group. Nothing in the
repository proves namespaces are globally unique across tenants, and the
projection manifest (`config/projections/facts-v8.yaml`) already declares scope
as `[tenant_id, namespace]`, so the live adapter contradicted its own contract.

Retrieval masked the leak for `memory.search`: `RetrievalPlanner` rehydrates
every projection hit from the canonical store and drops a record whose tenant
does not match (ADR-012). Graph intelligence cannot rely on that mask. A
traversal, neighborhood, community, or centrality result is computed over the
provider graph itself; a shared group lets another tenant's entities and edges
shape the answer before any record is rehydrated. Tenant-safe group identity is
therefore a P0 prerequisite for the graph-intelligence campaign.

The campaign pack specified the output form `l9g:v1:{sha256}`. Graphiti v0.30.2
(`graphiti_core/helpers.py::validate_group_id`) rejects any group id outside
`^[a-zA-Z0-9_-]+$` on `add_episode` and on every search path, so that literal
form would fail every projection write. The pack also requires the id to be
provider-safe ASCII; the separator is the only part that changes.

## Decision

1. `graph.scope` is the single derivation of provider group identity
   (GraphScopeKey v1):

   ```text
   material = canonical_json({"namespace": namespace, "tenant_id": tenant_id})
              (sorted keys, compact separators, UTF-8)
   digest   = sha256(material)
   group_id = "l9g-v1-" + digest_hex
   ```

2. `GraphitiProjection.project` writes each episode to
   `graph_group_id(record.tenant_id, record.namespace)`. The projection payload
   carries `scope_scheme` and `scope_digest`; it never carries the raw tenant id.
3. `ProjectionAdapter.search_strategy` and `search` take a required keyword
   `tenant_id`. `RetrievalPlanner` passes the server-derived tenant of the
   authenticated principal; namespaces remain the authorized set. Each
   namespace maps to exactly one derived group; no wildcard or prefix group is
   produced.
4. Retirement and erasure keep addressing episodes by the persisted locator
   (`delete_episode {uuid}`), so they remain correct for episodes projected
   under either scheme.
5. The Graphiti episode UUID remains the canonical `record_id`.

## Alternatives Considered

- Keep `group_id=namespace` and require globally unique namespaces.
- Prefix the raw tenant id (`<tenant>:<namespace>`).
- Rename existing provider groups in place.
- Use the pack's literal `l9g:v1:` form.

## Rejected Alternatives

- Globally unique namespaces are an unproven, unenforced assumption; the
  failure mode is silent cross-tenant graph exposure.
- A raw tenant prefix exposes tenant identity inside the provider graph and
  depends on provider escaping rules.
- In-place group rename is forbidden by the campaign scope contract: it has no
  atomic provider primitive and cannot be verified against canonical state.
- `l9g:v1:` is rejected by Graphiti v0.30.2 `validate_group_id`.

## Invariants

- GI-009: graph identity is scoped by both tenant and namespace.
- GI-010/GI-011: the tenant input is server-derived; no request field names,
  mints, or widens a group id (`MemorySearchRequest` forbids extra fields).
- GI-012: a multi-namespace read queries exactly the derived group per
  authorized namespace.
- The raw tenant id never appears in a provider group id or projection payload.
- GraphScopeKey derivation is deterministic across processes and releases.

## Consequences

- Projection writes and searches are tenant-isolated at the provider.
- Existing projected episodes live under namespace-named groups and are no
  longer searched by this release. Canonical search is unaffected; projection
  strategies return no hits for a namespace until its records are re-projected.
- Every `ProjectionAdapter` implementation must accept `tenant_id`.

## Security Impact

Closes cross-tenant co-location in the provider graph. Search hits were already
filtered by canonical rehydration; writes, provider-side scoring, and all future
structural operations were not. The scope digest is non-reversible without the
source scope.

## Migration Impact

No canonical schema change. The projection must be rebuilt from canonical
state; in-place rename is forbidden. Preferred cutover
(`docs/graph-intelligence/TENANT_SCOPE_MIGRATION.md`): provision a fresh
Graphiti database, deploy this release, run `l9-memory rebuild-projection` per
namespace, verify the dual-tenant collision fixture, then move the projection
binding. The old projection is retained for the rollback window and destroyed
only after deletion obligations are reconciled.

## Validation Requirements

- `tests/unit/test_graph_scope_key.py`: determinism, fixed test vector,
  tenant and namespace separation, Graphiti-safe charset, no raw tenant,
  empty-component rejection, exact multi-namespace set.
- `tests/security/test_graph_tenant_isolation.py`: two tenants writing the same
  namespace are projected into distinct groups; each tenant's search queries
  only its own group and returns only its own records; a provider hit naming
  another tenant's record is dropped; a request cannot supply a group id.
- `tests/unit/test_projection_strategies.py`: the official Graphiti dialect
  sends the derived group id, never the bare namespace.
- The existing projection, retrieval, and lifecycle suites stay green.

## Rollback Conditions

Revert this change and restore the previous projection binding if the rebuilt
projection cannot be verified against canonical state or the collision fixture
fails. Canonical memory is untouched in either direction; the old
namespace-keyed projection remains available until destroyed after cutover.

## Supersedes / Superseded By

Refines ADR-012 and ADR-025 for provider-side scope. Superseded by none.
