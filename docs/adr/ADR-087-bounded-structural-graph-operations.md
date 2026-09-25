# ADR-087: Bounded Structural Graph Operations

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-087-bounded-structural-graph-operations.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-09-25
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ (campaign `l9-memory-graph-intelligence-v1`, slice PR-D)

## Status

Accepted

## Context

ADR-085 and ADR-086 established a read-only port, governing service, and
typed receipts, with no structural operation served. The first capabilities
that need no analytics engine are bounded traversal, neighborhood expansion,
and path discovery over the Graphiti v0.30.2 schema:
`(:Entity)-[:RELATES_TO {group_id, fact, episodes, valid_at, invalid_at,
created_at, expired_at}]->(:Entity)` with provenance
`(:Episodic)-[:MENTIONS]->(:Entity)`, the episode UUID being the canonical
`record_id` (ADR-084).

## Decision

1. The Neo4j adapter serves `graph.traverse`, `graph.neighborhood`, and
   `graph.path` through static templates (`adapters/neo4j_graph_templates.py`):
   - Cypher cannot parameterize a variable-length bound, so each depth 1..6 and
     direction (`out`, `in`, `both`) is its own template. The family is expanded
     once at import from module constants into a closed set; every text passes
     the ADR-085 registration audit and no request value reaches query text.
   - Every relationship on a path must be an allowlisted type in an authorized
     group, valid at `as_of` (`valid_at <= as_of < invalid_at`), and current at
     `recorded_before` (created before it and not expired at it; without it,
     Graphiti-expired edges are excluded). Every node on the path must be in an
     authorized group, so a cross-tenant edge can never be crossed.
   - Row budgets are `max_edges + 1` (expansion) and `max_paths + 1` (paths);
     hitting a budget marks the provider result truncated.
2. Anchors resolve inside scope: an entity UUID is used as given (a foreign one
   simply matches nothing); a record id resolves to the entities its episode
   `MENTIONS`; text resolves through Graphiti's `node_name_and_summary` fulltext
   index with Lucene syntax escaped. At most ten entities per anchor.
3. Semantics: `traverse` follows the requested direction; `neighborhood` is
   direction-agnostic; depth 0 returns only the anchors; `path` returns all
   shortest paths up to `max_depth` (≥ 1) and is `COMPLETE` with no path
   results when none exists.
4. Supporting episodes: entities through `MENTIONS`, relationships through
   their `episodes` property (at most 50 each); ids that are not UUIDs are not
   evidence. The service then binds them to canonical records (ADR-086).
5. `graph.search` and `graph.semantic_search` are served by
   `GraphIntelligenceService` through the existing projection strategies with
   the principal's tenant; hits are admitted only after canonical rehydration,
   and unadmitted hits are counted without echoing their record ids.
   `memory.search` is unchanged (GI-036).
6. Service correction: node/edge/path caps now apply even when the provider
   reports truncation (the earlier short-circuit could return more items than
   `max_nodes`).

## Alternatives Considered

- One template with `*1..6` and a `length(p) <= $depth` filter.
- APOC path expanders.
- Graph Data Science for unweighted paths.
- Serve `graph.search` from the Neo4j adapter directly.

## Rejected Alternatives

- A fixed maximum bound with a post-filter lets the planner expand to depth 6
  on every request; per-depth templates keep the bound in the plan.
- APOC is an unaudited procedure surface and is refused by the query policy.
- GDS is unnecessary for bounded unweighted paths (08_ALGORITHM_POLICY).
- Direct fulltext search from the adapter would fork `memory.search`
  semantics; the projection strategies already own candidate retrieval.

## Invariants

GI-013, GI-014, GI-016, GI-017, GI-023, GI-024, GI-026, GI-029, GI-036.

## Consequences

- Structural answers are available with Neo4j alone; GDS is still optional.
- Directed and undirected traversal and all shortest paths are bounded by
  depth, row budget, runtime, and cardinality caps.

## Security Impact

Groups are checked on every node and relationship of every path, so a planted
cross-tenant edge is inert. Text anchors cannot inject Lucene syntax, and
Cypher never sees request text.

## Migration Impact

None. Additive templates and operations.

## Validation Requirements

- `tests/unit/test_neo4j_structural_operations.py` (scripted driver): full
  template family registered; depth 0; bound parameters and budgets; direction
  semantics; record/text anchor resolution and escaping; truncation; path
  preconditions and ordering; served capabilities.
- `tests/integration/test_neo4j_graph_traversal.py` (live Neo4j): depth 0/1/2,
  cross-tenant nodes/edges/records never appear, foreign entity anchors yield
  nothing, `as_of` excludes invalidated and future edges, direction, allowlist,
  record/text anchors, shortest path and no path, truncation, unknown anchor.
- `tests/unit/test_graph_service.py`: search operations, cap regression.

## Rollback Conditions

Revert the slice; the service reports the operations unavailable again.

## Supersedes / Superseded By

Extends ADR-085 and ADR-086. Superseded by none.
