# ADR-085: Graph Intelligence Port and Read-Only Neo4j Substrate

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-085-graph-intelligence-port-and-neo4j-substrate.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-09-25
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ (campaign `l9-memory-graph-intelligence-v1`, slice PR-B)

## Status

Accepted

## Context

`MemoryService` and `RecordStore` are canonical memory authority (ADR-002,
ADR-025). Graphiti is a rebuildable projection reached through
`ProjectionAdapter`, which owns project/retire/erase and graph/semantic
candidate retrieval (ADR-012, ADR-074). The projection can answer "which
memories are relevant" but cannot answer structural questions — how remembered
entities are connected, which paths matter, which nodes are central, which
communities exist.

Graphiti v0.30.2 stores its temporal knowledge graph in Neo4j 5.26 and Neo4j
Graph Data Science 2.13 is the compatible analytics engine. Reaching that graph
directly risks a second semantic graph writer, raw query exposure, and
provider-shaped contracts.

## Decision

1. `graph.ports.GraphIntelligencePort` is a provider-neutral **sibling** of
   `ProjectionAdapter`, not an extension of it. It owns bounded structural
   queries and analytics over the Graphiti-managed graph and exposes
   `capabilities()`, `health()` and `close()`; operations are added by later
   slices against typed contracts.
2. Capability names are the provider-neutral vocabulary `graph.search` …
   `graph.structural_embedding` (`GraphCapability`). A backend reports what it
   supports and what it implements separately; only the intersection is served,
   and an absent capability is never silently substituted (GI-032).
3. **Graphiti is the exclusive semantic graph-model writer.** The Neo4j adapter
   is read-only:
   - every statement is a named module-level template in a `QueryRegistry`;
     registration refuses `CREATE`, `MERGE`, `SET`, `DELETE`, `REMOVE`,
     `FOREACH`, `LOAD CSV`, index/constraint drops, `IN TRANSACTIONS`, GDS
     `write`/`mutate`/export, APOC and `dbms.*` other than `components`, and any
     run-time composition marker;
   - no method accepts query text; request values bind as parameters only;
   - every session is opened with `default_access_mode=READ` and runs through
     `execute_read` with a per-statement timeout; the server itself rejects a
     write in that transaction (`Neo.ClientError.Statement.AccessMode`);
   - deployment binds a credential separate from Graphiti's writer credential
     (`docs/graph-intelligence/NEO4J_BINDING.md`).
4. GDS V1 is stream/stats only; ephemeral in-memory catalog graphs are the only
   GDS state the adapter may create, and it must drop them (implemented with the
   analytics slice).
5. `neo4j>=5.26,<7` is the optional extra `graph-intelligence`. The package
   imports and runs without it. `graph_intelligence_backend: none | neo4j`
   (default `none`) selects `NullGraphIntelligence` or the Neo4j adapter;
   selecting `neo4j` without a URI or without the driver is a
   `ConfigurationError`. An unreachable server is a health state, not a
   construction failure, so canonical memory and Graphiti search are unaffected.
6. Health is multi-dimensional (`GraphBackendHealth`): reachability, backend
   version/edition, schema fingerprint and compatibility with the qualified
   binding, analytics version and missing procedures, and GraphScopeKey v1
   conformance of sampled projection groups (ADR-084). A reachable server with
   the wrong schema or namespace-keyed groups is unhealthy.
7. `MemoryRuntime` composes the adapter beside `MemoryService`; no caller
   reaches Neo4j except through it.

## Alternatives Considered

- Extend `ProjectionAdapter` with structural methods.
- Use the `graphdatascience` Python client.
- Make Neo4j a core dependency.
- Accept Cypher from trusted internal callers.

## Rejected Alternatives

- Extending `ProjectionAdapter` would fuse retrieval-candidate semantics,
  lifecycle operations, and analytics limits into one provider-shaped
  abstraction.
- The GDS client adds a dependency and a second execution surface; fixed
  parameterized procedure calls through the driver are auditable.
- A core Neo4j dependency would force every deployment to carry a driver it
  does not use.
- Any raw query input defeats the static audit and GI-006/GI-017.

## Invariants

- GI-002/GI-019: no persistent graph mutation is expressible through the
  adapter; mutation templates cannot be registered.
- GI-005/GI-008: credentials stay inside the adapter; health and config reprs
  never carry them; server notifications (which can echo query text) are off.
- GI-017: static parameterized templates only.
- GI-031/GI-032: missing GDS disables analytics only; detection is explicit.
- GI-033/GI-034: public contracts are provider-neutral; provider fields stay in
  health and receipt metadata.

## Consequences

- Graph intelligence can be enabled per deployment without affecting canonical
  memory or `memory.search`.
- Later slices add operations as registered templates and typed contracts.
- A new Graphiti construct does not enter traversal until the allowlist and the
  qualified fingerprint are updated.

## Security Impact

Read access mode plus a least-privilege reader credential plus a lexical
registration guard give three independent barriers against persistent writes.
Unreachable-backend probes are bounded by the query budget rather than the
driver's default 30 s transaction retry.

## Migration Impact

Additive. New settings default to `none`; no canonical or projection schema
change. `uv.lock` gains `neo4j` (and `pytz`) through the optional extra and the
dev extra.

## Validation Requirements

- `tests/unit/test_graph_query_policy.py`: every mutation/composition form is
  refused at registration; the adapter exposes no raw-query or mutation method;
  the adapter source opens only read transactions and runs only registered text.
- `tests/unit/test_neo4j_graph_intelligence_adapter.py`: health dimensions,
  bounded read sessions on the bound database, GDS absence, missing Graphiti
  constructs, fingerprint mismatch, non-conformant groups, unreachable backend,
  credential redaction.
- `tests/unit/test_graph_intelligence_factory.py`: explicit null default,
  settings validation, environment binding, missing-driver configuration error,
  package runs without the driver.
- `tests/integration/test_neo4j_graph_intelligence_live.py` (with
  `L9_MEMORY_TEST_NEO4J_URI`): live 5.26/2.13 versions and server-side write
  refusal on the adapter's read session.

## Rollback Conditions

Set `graph_intelligence_backend: none` (or revert). Nothing persistent is
created by this slice.

## Supersedes / Superseded By

Extends ADR-012 and ADR-013. Superseded by none.
