<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/graph-intelligence/USAGE.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->

# Graph Intelligence Usage

Decisions: ADR-084 (scope key) · ADR-085 (port, Neo4j) · ADR-086 (contracts,
evidence) · ADR-087 (traversal, paths) · ADR-088 (GDS analytics) · ADR-089
(surfaces, observability) · ADR-090 (Graphiti episode identity).

Graph intelligence is advisory projection intelligence. Every result item is
`authority_class: advisory_projection` and names the canonical records that
support it; unsupported observations are reported separately and never served
as authority.

## Operations

| Operation | MCP tool | Needs | Default algorithm |
|---|---|---|---|
| `graph.search` | `memory.graph.search` | Graphiti projection, `anchor.query` | `graphiti-graph-search` |
| `graph.semantic_search` | `memory.graph.semantic_search` | Graphiti projection, `anchor.query` | `graphiti-semantic-search` |
| `graph.traverse` | `memory.graph.traverse` | Neo4j, anchor | `bounded-traversal` (directed) |
| `graph.neighborhood` | `memory.graph.neighborhood` | Neo4j, anchor | `bounded-neighborhood` |
| `graph.path` | `memory.graph.path` | Neo4j, anchor + target, `max_depth ≥ 1` | `shortest-path` |
| `graph.centrality` | `memory.graph.centrality` | GDS | `pagerank` (`degree`, `betweenness`) |
| `graph.community` | `memory.graph.community` | GDS | `louvain` (`leiden`) |
| `graph.structural_embedding` | `memory.graph.structural_embedding` | GDS | `fastrp` (digests) |
| `graph.structural_similarity` | `memory.graph.structural_similarity` | GDS, anchor | `fastrp-cosine` |
| `graph.link_prediction` | `memory.graph.link_prediction` | GDS, anchor, flag + alpha ceiling | `adamic-adar` |

`memory.graph.capabilities` reports what is served right now and why the rest
is not.

On real Graphiti, `graph.search` (entity-node search) returns no canonical
support: Graphiti entities carry no episode reference. Prefer
`graph.semantic_search`, or a structural operation with `anchor.query`
(see [QUALIFICATION.md](QUALIFICATION.md)).

## Request

```json
{
  "namespaces": ["repo-a"],
  "anchor": {"entity_uuid": "…"},
  "target": {"record_id": "…"},
  "relationship_types": ["RELATES_TO"],
  "direction": "both",
  "as_of": "2026-09-01T00:00:00Z",
  "limits": {"max_depth": 2, "max_nodes": 100, "max_edges": 250, "max_paths": 10, "max_runtime_ms": 3000}
}
```

There is no tenant field: the tenant is the authenticated principal's. There
is no query-text field for the database: statements are fixed server-side.

## SDK

```python
from l9_graphite_memory.graph.contracts import GraphAnchor, GraphIntelligenceRequest

receipt = sdk.graph(
    GraphIntelligenceRequest(
        operation="graph.neighborhood",
        namespaces=("repo-a",),
        anchor=GraphAnchor(query="deployment pipeline"),
    )
)
if receipt.status == "COMPLETE":
    for item in receipt.results:
        ...  # item["supporting_record_ids"] -> canonical memory
```

## Receipt status

| Status | Meaning |
|---|---|
| `COMPLETE` | provider answered; results are bound to canonical support (possibly empty) |
| `PARTIAL` | truncated, items dropped as out of scope, rehydration or catalog-cleanup problem |
| `FAILED` | refused by policy, capability unavailable, or provider error; no results |

A `required: true` request turns any `PARTIAL` into `FAILED`.

## Enabling the backend

See [NEO4J_BINDING.md](NEO4J_BINDING.md) for settings and the least-privilege
reader, and [TENANT_SCOPE_MIGRATION.md](TENANT_SCOPE_MIGRATION.md) before
pointing it at an existing Graphiti database.
