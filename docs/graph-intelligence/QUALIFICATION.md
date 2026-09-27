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
| `graphiti-core` | 0.30.2 | real: `add_episode` pipeline, LLM extraction, node/edge resolution, persistence, indices, search, `remove_episode` |
| Neo4j | 5.26.31 Community | real |
| Neo4j GDS | 2.13.13 | real |
| `neo4j` Python driver | 6.3.1 | real |
| LLM | OpenAI `gpt-5.5` (`MODEL_NAME`), small `gpt-4.1-nano` (`SMALL_MODEL_NAME`) | real |
| Embedder | `text-embedding-3-large`, 3072 dims, read from `config/projections/facts-v8.yaml` | real |
| Cross-encoder | `OpenAIRerankerClient` on the small model | real |
| MCP transport | `GraphitiCoreTransport` (test only) | substituted: calls `graphiti_core` in process using the official tool names, replies and swallowed-failure semantics |

The model stack is the one settled by the GAR intelligence harvest (ADR-092):
the Graphiti deployment's OpenAI provider, with `gpt-4o-mini` replaced by
graphiti-core 0.30.2's own defaults, and the embedder the projection manifest
pins. There are no stand-in models.

The production code under test is unmodified: `GraphitiProjection`,
`OutboxWorker`, `MemoryService`, `SQLiteRecordStore`,
`Neo4jGraphIntelligence` and `GraphIntelligenceService`.

## Model route and credentials

`L9_QUAL_MODEL_ROUTE` selects how the same OpenAI models are reached:

| Route | Endpoint | Credential (Infisical / Actions secret) |
|---|---|---|
| `openai` (default) | api.openai.com | `OPENAI_API_KEY` |
| `openrouter` | OpenRouter's OpenAI-compatible API, models prefixed `openai/` | `OPENROUTER_API_KEY` |

The route is explicit and recorded in the run's model-stack receipt; one route
never falls back to the other. A missing credential fails the run. Keys are
read from the environment (CI imports the Actions secret) or bound in-process
(`tests.qualification.graphiti_harness.KEY_PROVIDER`), never logged or
written to a file.

## What passed (15 tests)

| Test | Proves |
|---|---|
| `test_projection_ingests_named_episodes_with_provider_uuids` | canonical write → outbox → real Graphiti episodes named `memory:<record_id>` in the tenant's GraphScopeKey group, with provider uuids and name locators; no tenant id in content |
| `test_graphiti_rejects_a_caller_supplied_episode_uuid` | the upstream defect ADR-090 routes around |
| `test_graphiti_extraction_builds_scoped_entities_and_edges` | real extraction keeps every entity and edge in one group; two tenants sharing a namespace get separate graphs; neither tenant's text leaks into the other's |
| `test_backend_health_qualifies_the_real_graphiti_schema` | schema, analytics and scope-conformance checks accept a real Graphiti database |
| `test_record_anchor_resolves_through_the_episode_name_and_binds_support` | record anchors resolve through `MENTIONS`; support rehydrates to the tenant's own records |
| `test_another_tenant_cannot_reach_the_graph_through_a_shared_namespace` | tenant B cannot reach tenant A's graph through A's record id; B's graph binds only B's record |
| `test_path_and_neighborhood_over_the_real_graph` | a bounded path Falcon → Ledger exists within 3 hops; depth-1 neighborhood reaches Payments |
| `test_gds_analytics_over_the_real_graph` (×3) | PageRank, Louvain and FastRP complete with canonical support and leave no `l9gi_` catalog graph |
| `test_fact_search_maps_episodes_back_to_canonical_records` | fact search maps episodes back to canonical records, per tenant |
| `test_entity_node_search_binds_canonical_support_on_real_graphiti` | `graph.search` entity hits bind to the tenant's records (ADR-092) |
| `test_supersession_and_verified_erasure_remove_real_episodes` | supersession withdraws, and verified erasure removes, the real episode; no edge still cites it |
| `test_graphiti_process_restart_recovers_and_keeps_the_projection` | a new Graphiti process keeps the projection and keeps projecting |
| `test_the_qualified_model_stack_is_the_harvested_one` | receipt of the model stack and route the run used |

Real extraction is not deterministic, so assertions are properties (scoping,
provenance, support, lifecycle), never exact graphs. The suite ran green three
consecutive times on Neo4j 5.26.31 + GDS 2.13.13.

CI runs it nightly and on dispatch (`.github/workflows/graph-qualification.yml`)
and fails on a skip. The deterministic live suites, including Neo4j outage and
restart, run on every PR (`ci.yml` job `graph-live`).

Local command (the harness needs `graphiti-core`, which is not a project
dependency):

```bash
uv venv -p 3.13 .qualvenv
uv pip install -p .qualvenv/bin/python 'graphiti-core==0.30.2' httpx pytest \
  pytest-asyncio jsonschema pyyaml 'neo4j>=5.26,<7'
PYTHONPATH=src:. L9_MEMORY_TEST_NEO4J_URI=bolt://127.0.0.1:7687 \
  L9_MEMORY_TEST_NEO4J_PASSWORD=... L9_QUAL_MODEL_ROUTE=openai \
  .qualvenv/bin/python -m pytest tests/qualification
```

`graphiti-core` 0.30.2 imports `httpx` without declaring it, so it is
installed explicitly. Without `graphiti_core` or `L9_MEMORY_TEST_NEO4J_URI`
the suite skips locally; CI fails on that skip.

## What this does not qualify

- **Extraction quality at scale.** The fixture corpus is a few short
  episodes; entity resolution and deduplication over a production corpus are
  not measured.
- **The official MCP server process.** Its tool bodies were read, and the
  harness reproduces their replies; the HTTP server was not run.
  `test_graphiti_http_projection_loop.py` covers the wire dialect.
- **Enterprise RBAC.** The least-privilege reader grants in `NEO4J_BINDING.md`
  need Enterprise edition; the local server is Community.
- **Scale.** Fixture graphs are small. `gds_max_nodes`, the traversal budgets
  and `episode_lookup_limit` are tuned during cutover
  ([CUTOVER_RUNBOOK.md](CUTOVER_RUNBOOK.md)), against the real graph.

## Schema fingerprint

The qualification database reported
`134a8b34789d32e7c6b75fe0cd6329b945fabaa830cab1f52bb6be23172df03e`. The
fingerprint covers database-wide labels, relationship types and the relied-on
property keys, so it depends on everything stored in that database. Record
your own production value in `graph_expected_schema_fingerprint` rather than
reusing this one.
