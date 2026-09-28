<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/graph-intelligence/QUALIFICATION.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->

# Graph Intelligence Live Qualification (GI-080)

Decision: ADR-090. Suite: `tests/qualification/test_graphiti_live_qualification.py`.

## Qualified stack

| Component | Version | Real or substituted |
|---|---|---|
| `graphiti-core` | 0.30.2 | real: `add_episode` pipeline, node/edge resolution, persistence, indices, search, `remove_episode` |
| Neo4j | 5.26.31 Community | real |
| Neo4j GDS | 2.13.13 | real |
| `neo4j` Python driver | 6.3.1 | real |
| LLM | `ScriptedExtractionLLM` | substituted: answers Graphiti's prompts from `[[A->B]]` markers |
| Embedder | `HashEmbedder` (1024-d token hashes) | substituted |
| Cross-encoder | `OverlapReranker` | substituted |
| MCP transport | `GraphitiCoreTransport` (test only) | substituted: calls `graphiti_core` in process using the official tool names, replies and swallowed-failure semantics |

The production code under test is unmodified: `GraphitiProjection`,
`OutboxWorker`, `MemoryService`, `SQLiteRecordStore`,
`Neo4jGraphIntelligence` and `GraphIntelligenceService`.

## What passed (13 tests)

| Test | Proves |
|---|---|
| `test_projection_ingests_named_episodes_with_provider_uuids` | canonical write → outbox → real Graphiti episodes named `memory:<record_id>` in the tenant's GraphScopeKey group, with provider uuids, name locators, no tenant id in content |
| `test_graphiti_rejects_a_caller_supplied_episode_uuid` | the upstream defect ADR-090 routes around: supplying `uuid` yields "queued" and `NodeNotFoundError`, and no episode |
| `test_graphiti_extraction_builds_scoped_entities_and_edges` | Graphiti's own persistence keeps every entity and `RELATES_TO` edge in one group; same namespace, two tenants, two graphs |
| `test_backend_health_qualifies_the_real_graphiti_schema` | the adapter's schema, analytics and scope-conformance checks accept a real Graphiti database |
| `test_record_anchor_resolves_through_the_episode_name_and_binds_support` | record anchors resolve via `MENTIONS` from the named episode; support rehydrates to both records |
| `test_another_tenant_cannot_reach_the_graph_through_a_shared_namespace` | tenant B, same namespace, cannot reach tenant A's graph through A's record id; B's own graph binds only B's record |
| `test_path_and_traversal_over_the_real_graph` | shortest path Falcon → Ledger has length 2; directed depth-1 traversal |
| `test_gds_analytics_over_the_real_graph` (×3) | PageRank, Louvain and FastRP complete with canonical support and leave no `l9gi_` catalog graph |
| `test_fact_search_maps_episodes_back_to_canonical_records` | Graphiti fact search results map through their episodes to canonical records, per tenant |
| `test_entity_node_search_has_no_canonical_mapping_on_real_graphiti` | known limitation, stated as a test (below) |
| `test_supersession_and_verified_erasure_remove_real_episodes` | supersession withdraws, and verified erasure removes, the real episode through name resolution; Graphiti drops the edge only that episode supported |

Command (the harness needs `graphiti-core`, which is not a project
dependency):

```bash
uv venv -p 3.13 .qualvenv
uv pip install -p .qualvenv/bin/python 'graphiti-core==0.30.2' httpx pytest \
  pytest-asyncio jsonschema pyyaml 'neo4j>=5.26,<7'
PYTHONPATH=src:. L9_MEMORY_TEST_NEO4J_URI=bolt://127.0.0.1:7687 \
  L9_MEMORY_TEST_NEO4J_PASSWORD=... .qualvenv/bin/python -m pytest tests/qualification
```

`graphiti-core` 0.30.2 imports `httpx` without declaring it, so it is
installed explicitly. Without `graphiti_core` or `L9_MEMORY_TEST_NEO4J_URI`
the suite skips, as it does in CI.

## What this does not qualify

- **LLM extraction quality.** Entities and edges come from scripted markers, so
  entity resolution, deduplication and temporal extraction by a real model are
  not exercised.
- **Embedding and rerank quality.** Hash vectors make search deterministic but
  say nothing about semantic recall.
- **The official MCP server process.** Its tool bodies were read, and the
  harness reproduces their replies; the HTTP server was not run.
  `test_graphiti_http_projection_loop.py` covers the wire dialect.
- **Enterprise RBAC.** The least-privilege reader grants in `NEO4J_BINDING.md`
  need Enterprise edition; the local server is Community.
- **Scale.** Fixture graphs are small. `gds_max_nodes`, the traversal budgets
  and `episode_lookup_limit` are exercised by unit tests only.
- **Production cutover (GI-090).** No deployment was changed. Cutover is an
  operator step: bind `graph_*` settings, run `rebuild-projection` for records
  projected before ADR-084/ADR-090, check `memory.graph.capabilities`, then set
  `graph_intelligence_required` if graph readiness should gate `/readyz`.

## Known limitation

Graphiti `search_nodes` returns entities with name and summary only. Entities
carry no episode reference, so `graph.search` has no canonical support to bind
and answers COMPLETE and empty. Use `graph.semantic_search` (facts cite
episodes) or a structural operation anchored on the query (`anchor.query`
resolves through the fulltext index and binds support via `MENTIONS`).

## Schema fingerprint

The qualification database reported
`134a8b34789d32e7c6b75fe0cd6329b945fabaa830cab1f52bb6be23172df03e`. The
fingerprint covers database-wide labels, relationship types and the relied-on
property keys, so it depends on everything stored in that database. Record
your own production value in `graph_expected_schema_fingerprint` rather than
reusing this one.
