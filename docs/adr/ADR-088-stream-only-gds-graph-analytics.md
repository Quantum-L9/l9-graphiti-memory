# ADR-088: Stream-Only GDS Graph Analytics

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-088-stream-only-gds-graph-analytics.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-09-25
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ (campaign `l9-memory-graph-intelligence-v1`, slice PR-E)

## Status

Accepted

## Context

After ADR-087 the graph-intelligence plane answers connectivity questions.
The remaining V1 capabilities — centrality, community detection, structural
embeddings, structural similarity, and link prediction — need a graph-analytics
engine. Neo4j Graph Data Science 2.13 is the compatible engine for Neo4j 5.26.
GDS can write results back into the database (`write`, `mutate`, export),
which would make it a second semantic graph writer beside Graphiti.

## Decision

1. **Stream mode only.** Analytics run through `gds.<algorithm>.stream`
   templates (`adapters/neo4j_gds_templates.py`); `write`, `mutate`, and
   export are refused by the registration audit (ADR-085) and absent from the
   template set.
2. **Ephemeral, scope-bound projections.** Each operation:
   - measures the authorized scope (`gds_scope_size_v1`) and refuses before
     projecting when it exceeds `graph_gds_max_nodes`;
   - projects only `RELATES_TO` edges whose endpoints and edge are in the
     authorized GraphScopeKey groups and pass the allowlist and the
     valid-time/transaction-time filters, with a Cypher aggregation
     `gds.graph.project` (natural, reverse, or undirected by direction);
   - streams one algorithm, then drops the catalog graph in `finally`.
   Catalog names are `l9gi_<operation digest>_<random>` — never a tenant or
   namespace. A failed drop is reported as `gds_catalog_cleanup_failed`
   (receipt `PARTIAL`) and counted; `cleanup_stale_catalog()` sweeps every
   `l9gi_` graph left by a crash.
3. **Algorithms** (all `concurrency: 1`, fixed seeds, so identical scopes give
   identical receipts):
   - centrality: PageRank (default), Degree, Betweenness;
   - community: Louvain (default), Leiden (undirected only);
   - structural embedding: FastRP (dimension 64, seed 42); callers receive a
     digest and dimension, raw vectors only when the deployment allows;
   - structural similarity: cosine over streamed FastRP vectors relative to an
     anchor entity; there is no semantic-embedding substitute;
   - link prediction (alpha, feature-gated at the adapter and the service):
     Adamic–Adar (default), common neighbours, resource allocation, computed in
     Cypher over common neighbours and their **in-scope** degrees. The
     `gds.alpha.linkprediction.*` functions are not used because they count
     neighbours across the whole database, outside the authorized groups.
     Predicted links are candidates in a receipt and are never materialized.
4. **Capability detection.** Analytics are served only when GDS reports a
   version and every required stream procedure exists; otherwise they are
   unavailable while traversal/path keep working (GI-031).

## Alternatives Considered

- GDS `mutate`/`write` to cache results.
- Native projections by label/type.
- GDS link-prediction functions or ML pipelines.
- Default GDS concurrency.

## Rejected Alternatives

- Persistent writes violate the Graphiti writer law (GI-020/GI-021).
- Native projections cannot filter by group or temporal validity, so they would
  project other tenants' graphs into the analysis.
- GDS link-prediction functions leak cross-scope degree; pipelines are beta and
  need training state.
- Parallel execution makes Louvain/Leiden/FastRP non-deterministic and uses
  shared cores (Community Edition caps at four).

## Invariants

GI-013, GI-015, GI-018, GI-020, GI-021, GI-022, GI-028, GI-031, GI-032.

## Consequences

- All ten V1 graph-intelligence capabilities have an implementation.
- Analytics cost is bounded by the node ceiling, the relationship ceiling
  (20 × node ceiling, marked truncated when exceeded), the runtime budget, and
  single-threaded execution.

## Security Impact

Projection filters make another tenant's subgraph invisible to the algorithm;
catalog names reveal no scope; nothing is written back.

## Migration Impact

None. Requires GDS 2.13 with `dbms.security.procedures.unrestricted=gds.*`
for analytics; without it analytics report unavailable.

## Validation Requirements

- `tests/unit/test_neo4j_gds_operations.py` (scripted driver): no
  write/mutate/export template; project → stream → drop order with an opaque
  name; drop on stream failure; drop failure → `PARTIAL`; ceiling refusal
  before projection; empty scope; Leiden direction; orientation; unknown
  algorithms; cosine ranking; in-scope link scoring; disabled link prediction;
  stale sweep.
- `tests/integration/test_neo4j_gds_analytics.py` (live Neo4j 5.26 + GDS
  2.13): centrality ranks the hub, communities separate the triangles,
  FastRP is digested and deterministic, similarity excludes the anchor,
  link prediction adds no relationship, ceiling refusal, drop on failure,
  stale sweep, and no tenant-B identifier in any receipt.

## Rollback Conditions

Revert the slice; analytics report unavailable. Remove GDS to disable at
runtime.

## Supersedes / Superseded By

Extends ADR-085..ADR-087. Superseded by none.
