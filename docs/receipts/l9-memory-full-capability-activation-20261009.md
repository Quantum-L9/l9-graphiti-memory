<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/receipts/l9-memory-full-capability-activation-20261009.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.6.0
updated: 2026-07-22
/L9_META -->

# L9 full-capability memory activation: capability closure receipt

Mission `L9 Full-Capability Memory Activation`, recorded 2026-10-09. This
receipt binds the census, the product repair, the operational proof and the
consumer handoff to exact revisions. It admits nothing: it does not retarget
the published 2.6.0 release, does not bind a consumer, and does not authorize a
deployment change.

| Coordinate | Value |
|---|---|
| Product revision censused | `Quantum-L9/l9-graphiti-memory@24a579b46855b59328e67b6106f9f29a16a56ec5` (main) |
| Product repair branch | `agent/claude-code/full-capability-memory-activation`, from the revision above |
| Published release (immutable) | `l9-graphite-memory` 2.6.0, source `846f283f…`, wheel `d4935732…`, sdist `537ff040…` |
| Semantic authority | `Quantum-L9/.github@976eedb58358355919a7eb39b4c78bd52a54a102` |
| Consumer governance | `Quantum-L9/Cursor-Governance@9378c4a` (main); PR #708 head `faaf83c` (staging binding text, not live proof) |
| Open product PR respected | #89 `docs(readme): state consumer-selected full-capability deployment obligations` (head `2d97fed`); its README hunk is untouched here |
| Decision record | ADR-097 |

## A. Capability closure matrix

States: **VERIFIED** (implemented, reachable, verified on a real substrate in
this session), **SATISFIED** (already satisfied before this session, evidence
cited), **BLOCKED** (exact cause, owner and proof request). Classification is
the mission's: `REQUIRED_ACTIVE`, `REQUIRED_SHADOW`, `DEFERRED_BY_DESIGN`.

Evidence keys: `PG` = local PostgreSQL 16.15 at `127.0.0.1:55432`; `RD` =
local authenticated Redis 7.0.15 at `127.0.0.1:56379` with `volatile-lru`;
`N4` = local Neo4j 5.26.0 with GDS 2.13.13 (the CI-qualified pair) at
`127.0.0.1:57687`; `CI` = the workflow job named.

### Canonical memory

| Capability | Class | Owner | Activation path | Evidence | Status |
|---|---|---|---|---|---|
| Shared PostgreSQL canonical store | REQUIRED_ACTIVE | package | `L9_MEMORY_STORE_BACKEND=postgres` + `L9_MEMORY_POSTGRES_DSN` → `build_store` → every surface | `PG`: 125 passed, 0 failed (store contract, shared store, phase-lock atomicity, outbox leases, projection targets, maintenance, source invalidation); composed from settings in `test_full_capability_readiness_live.py` (`PG`+`RD`+`N4`: 10/10 passed) | VERIFIED |
| MemoryService-controlled writes, reads, lifecycle, receipts | REQUIRED_ACTIVE | package | `MemoryService` only; bypass scanner `check_memory_write_bypass` PASS | full suite in CI shape: 1618 passed, 51 skipped, 0 failed | SATISFIED |
| Safe backend transition (ADR-077) | REQUIRED_ACTIVE | package | `detect_backend_transition` on every `build_store` | `tests/unit/test_backend_transition_guard.py` (8 cases) | SATISFIED. Limitation by design: a move between two remote backends is not detected (RUNBOOK "Changing backends") |
| Canonical restart recovery (outbox resume, leases) | REQUIRED_ACTIVE | package | durable intents, `FOR UPDATE SKIP LOCKED` claims | `PG`: `test_outbox_leases.py` incl. concurrent-worker case | SATISFIED |
| Canonical backup and restore drill on the target | REQUIRED_ACTIVE | consumer deployment | RUNBOOK "Backup and restore" (SQLite sequence); PostgreSQL uses the operator's `pg_dump`/restore | repository proof covers SQLite byte-exact restore only (`tests/deployment/generated_data/test_backup_restore.py`) | BLOCKED: no authorized target store to drill. Owner: Cursor-Governance / Hetzner deployment owner. Proof: restore into an empty store, then `l9-memory readiness` COMPLETE and a representative historical search |

### Active memory

| Capability | Class | Owner | Activation path | Evidence | Status |
|---|---|---|---|---|---|
| `RedisActiveStore` | REQUIRED_ACTIVE | package | `L9_MEMORY_ACTIVE_BACKEND=redis` → `build_active_memory` (new) | `RD`: store contract Redis leg 20 passed; live suite | VERIFIED (was implemented but unreachable from settings at `24a579b`) |
| `RedisAwarenessBus` | REQUIRED_ACTIVE | package | same binding | `RD`: bus contract Redis leg 6 passed (fixture newly parameterized); live delivery of registration, context-update, drain and unregister pointers between two consumers | VERIFIED (was never instantiated, even by a test, at `24a579b`) |
| Supported `ActiveAgentClient` integration (ADR-067) | REQUIRED_ACTIVE | package | `build_runtime().active_memory.client()` / `build_active_memory(settings).client()`; adapters stay out of `active.__all__` | `test_active_memory_runtime.py` (14), `check_active_memory_public_api` OK (33 symbols) | VERIFIED (the factory ADR-067 names did not exist at `24a579b`) |
| Registration, presence, leases, heartbeats, context, awareness, resynchronization, cleanup | REQUIRED_ACTIVE | package | session lifecycle over the bound adapters | `RD`: conformance + `tests/external_runtime` (in-memory) + live suite | VERIFIED. Finding, not blocking: presence `status` stays `STARTING` for the instance's life (renew copies it); the committed context carries the agent status |
| Two independent agents sharing permitted real-time state | REQUIRED_ACTIVE | package | two bindings, two connections, one deployment identity | `RD`: `test_two_independent_consumers_share_state_through_redis` (presence, peer context, awareness, deployment isolation) | VERIFIED |
| No direct adapter access when the SDK forbids it | REQUIRED_ACTIVE | package | binding is the only construction path | `check_active_memory_public_api`; docs corrected (`docs/ACTIVE_MEMORY_SDK.md` named a non-existent package and told consumers to hand-build) | VERIFIED |
| Credential boundary (ADR-066) reaches the adapters | REQUIRED_ACTIVE | package | exactly one of `url_env` / `url_file` / `password_file`+host / `secret_reference`; resolver called at construction; only the source name is recorded | `test_factory_resolves_the_named_credential_source_without_connecting`, `…fails_closed_on_an_unresolvable_credential`; `check_secrets` PASS | VERIFIED (resolver was unreferenced by `src/` at `24a579b`) |
| Startup capability probe (deployment contract item 6) | REQUIRED_ACTIVE | package | `RedisActiveStore.health()` PING + scalar + sorted set; `RedisAwarenessBus.health()` PING + PUBLISH | `RD`: probe steps reported `["ping","scalar","sorted_set"]` / `["ping","publish"]` in readiness; unreachable backend → typed unavailable | VERIFIED (was a bare PING returning hard-coded "authenticated") |
| Redis outage and recovery | REQUIRED_ACTIVE | package | ADR-067 state machine | `RD`: real `shutdown nosave` / restart; session DEGRADED → re-registers through RESYNCHRONIZING after the lease lapsed; canonical write and search unaffected; readiness FAILED then ready | VERIFIED (recovery after an outage longer than the lease TTL ended the heartbeat loop permanently at `24a579b`; regression test fails without the fix) |
| Restricted-ACL conformance fixture (ADR-068) | DEFERRED_BY_DESIGN | package | `render_active_memory_redis_acl.py` | ADR-068 defers automated command-drift enforcement; CI Redis runs without ACL | DEFERRED_BY_DESIGN; the probe now exercises the exact command set under the deployment prefix, so a restricted ACL that refuses one is reported as `insufficient_acl` |

### Projection memory

| Capability | Class | Owner | Activation path | Evidence | Status |
|---|---|---|---|---|---|
| Compiled projection-manifest runtime (`config/projections/facts-v8.yaml`) | REQUIRED_ACTIVE | package | `L9_MEMORY_PROJECTION_RUNTIME=manifest` + `L9_MEMORY_PROJECTION_MANIFEST` → `build_projection_runtime` | `validate_projection_manifests` PASS; `test_projection_runtime.py`, `test_projection_targets.py` on `PG` (26 postgres cases) | SATISFIED in composition; opt-in by design (default is legacy) |
| Graphiti MCP active target: delivery, links, reconciliation, retirement, verified deletion | REQUIRED_ACTIVE | package + consumer deployment | `GRAPHITI_MCP_URL`/`GRAPHITI_MCP_TOKEN`, target `primary` | official-dialect in-process server: full loop, session re-establishment, wire dialect (`test_graphiti_http_projection_loop.py`); readiness projection family joins the verdict against it (`test_the_projection_family_joins_the_verdict_when_graphiti_is_bound`); in-process `graphiti-core` 0.30.2 qualification (nightly, needs a model key) proves extraction, search, erasure and process restart through a test transport, not the MCP server | VERIFIED on a sandbox-run official server (Phase 5, section E: `GM` delivery, links, retrieval, retirement, verified deletion, rebuild, readiness projection family); `tests/qualification` 15 passed, 0 skipped through the OpenRouter route (the Infisical `OPENAI_API_KEY` is rejected by OpenAI with 401; `OPENROUTER_API_KEY` works). BLOCKED for the deployment's own endpoint: none is reachable from this session or CI. Owner: deployment owner (Graphiti MCP endpoint + model key). Proof: `l9-memory readiness` projection family healthy against the deployed endpoint, one write delivered (`graph-cutover-status` confirmed count > 0), one verified deletion removing the episode |
| Zep shadow target | REQUIRED_SHADOW | package + consumer | `facts:v8:zep:primary` in manifest mode with `ZEP_API_KEY` | shadow isolation: planner never queries shadow targets unless measurement is on; shadow failures never change hits, scores, status (`test_projection_targets.py:766-797`); shadow health never degrades (`test_projection_runtime.py:345`) | BLOCKED for live delivery: no Zep subscription key held. Owner: consumer (subscription). Proof: shadow link recorded per write with canonical retrieval unchanged. Repaired (Phase 5, seam 4): the real `zep-cloud` 3.25 client rejected every delivery (`group_id` is the pre-3.0 spelling; `graph_id` is the graph), so no shadow write could ever have landed; failure accounting and zero influence are proven against the real client bound to an unreachable port. Finding: the Zep adapter's fixed tool list has no search tool, so `search_strategy` raises for Zep; harmless while shadow is never retrieved, but a future active Zep target would fail closed |
| Shadow results never contaminate canonical retrieval | REQUIRED_SHADOW | package | `retrieval/planner.py` iterates `active_targets()` only | unit evidence above | SATISFIED |
| Independent provider delivery and partial failure | REQUIRED_ACTIVE | package | one outbox intent per target | fakes: Zep down/Graphiti delivers and vice versa, partial erasure stays pending; `PG`-backed matrices | SATISFIED (fake providers; live see BLOCKED rows) |

### Graph intelligence

| Capability | Class | Owner | Activation path | Evidence | Status |
|---|---|---|---|---|---|
| Neo4j read-only graph intelligence | REQUIRED_ACTIVE | package | `L9_MEMORY_GRAPH_BACKEND=neo4j` + URI/user/password → `build_graph_intelligence` → MCP tools and SDK | `N4`: 27/27 live passed on rerun (first run: 1 `runtime_budget_exceeded` on cold GDS JIT within the 3 s default budget, environmental; the fixture's `warm_analytics` exists for this); CI `graph-live` | VERIFIED |
| GDS stream-only analytics | REQUIRED_ACTIVE | package | runtime detection; maturity ceiling | `N4`: centrality, community, FastRP, similarity, link prediction gated; catalog dropped | VERIFIED |
| Namespace-scoped queries, capability reporting, independent health | REQUIRED_ACTIVE | package | server-derived `l9g-v1` scope; `memory.graph.capabilities`; `/readyz` graph family | `N4`: cross-tenant isolation, foreign anchor refusal; readiness graph family selected+healthy with `analytics_available: true` from a settings-composed runtime | VERIFIED |
| Neo4j outage and restart | REQUIRED_ACTIVE | package | typed unreachable health, recovery | `N4`: `test_neo4j_restart_outage_live.py` passed with local stop/start | VERIFIED |

### Readiness and recovery

| Capability | Class | Owner | Activation path | Evidence | Status |
|---|---|---|---|---|---|
| Independent canonical, active-memory/awareness and graph/projection evidence | REQUIRED_ACTIVE | package | `MemoryRuntime.readiness()` → `ReadinessReport` with five families (new) | `test_readiness_reports_every_family_independently`; `PG`+`RD`+`N4` composed runtime | VERIFIED (active memory had no health surface at `24a579b`) |
| Aggregate full-capability verdict | REQUIRED_ACTIVE | package | `ready` and `full_capability`; `l9-memory readiness` exit code; `/readyz` 503 | live: `full_capability` true only when the projection family is bound; false otherwise | VERIFIED |
| Explicit degradation and restoration | REQUIRED_ACTIVE | package | required → FAILED; optional → PARTIAL; recovery observed | `RD` outage case; `N4` restart case | VERIFIED |
| No false green for a required absent or unproven capability | REQUIRED_ACTIVE | package | required + not selected → FAILED with reason | `test_a_required_active_memory_that_is_absent_is_never_green`; live `test_a_required_family_that_is_not_configured_is_never_green` | VERIFIED |
| Clean shutdown | REQUIRED_ACTIVE | package | `MemoryRuntime.close()` releases graph, active adapters, store | `tests/external_runtime/test_graceful_shutdown.py`; live suites close bindings on every path | SATISFIED |
| Consumer-reachable readiness from the governance side | REQUIRED_ACTIVE | consumer | `ops/memory` readiness ladder consuming `ReadinessReport` | not in this repository | BLOCKED: consumer change (handoff C.4) |

## B. Product repair (this branch)

Minimum necessary changes, all package-owned, no new `src/` files (142
production files, unchanged count):

- `config/models.py`, `config/loader.py`: active-memory settings and
  `L9_MEMORY_ACTIVE_*` bindings with fail-closed validation (identity,
  exactly one credential source, lease TTL above the heartbeat interval).
- `adapters/factory.py`, `adapters/__init__.py`: `build_active_memory`.
- `active/client.py`: `ActiveMemoryBinding`, `ActiveMemoryHealth`,
  `get_peer_context`, lifecycle pointer events, the ADR-067 recovery fix.
- `active/redis_adapters.py`: capability probes, typed subscribe errors,
  scope filtering parity with the reference adapter.
- `active/__init__.py`, `active/null_adapters.py`: exports and the real
  setting name in the disabled message.
- `runtime.py`, `contracts/receipts.py`, `contracts/__init__.py`:
  `MemoryRuntime.active_memory`, `readiness()`, `ReadinessReport`,
  `ReadinessFamily`.
- `server.py` `/readyz`, `cli.py` `readiness`.
- Tests: `tests/unit/test_active_memory_runtime.py`,
  `tests/conformance/active/conftest.py` (bus parameterized),
  `tests/integration/test_active_memory_redis_live.py`,
  `tests/integration/test_full_capability_readiness_live.py`.
- CI: `full-capability-live` job (PostgreSQL + Redis + Neo4j/GDS, fails on
  skip); `graph-live` set-check exclusion.
- Docs: ADR-097, `docs/ACTIVE_MEMORY_SDK.md`,
  `docs/ACTIVE_MEMORY_DEPLOYMENT_CONTRACT.md`, RUNBOOK, example config.
- Phase 5 (section E): `adapters/graphiti_projection.py` rank-derived scores
  for unscored provider hits (ADR-091 item 5 amended); `zep_transport.py`
  `graph_id`; `active/client.py` stale-presence cleanup on re-registration
  and the review fixes (`redis_adapters.py` structured authentication
  failures, `runtime.py` `aclose()` and `secret_provider` threading).
- Tests: `tests/integration/test_projection_seams_live.py` (11 seams; 10 in
  CI shape, seam 2 live only), `tests/unit/test_graphiti_projection_episode_identity.py`
  rank scoring, `tests/unit/test_active_memory_runtime.py` refused credential,
  `tests/unit/test_zep_transport.py` keyword lock.
- Assurance pins: ADR ledger 97, V-001 `1630 passed` (CI shape: PostgreSQL
  and Redis, no Neo4j, no server control; 52 skips enumerated in the pin).

Validation on this branch: `ruff check .` clean; `mypy src/l9_graphite_memory`
clean; `bash scripts/validate_release.sh` in CI shape (see the PR body for the
run); live suites as cited in the matrix.

Not changed: `product-topology.yaml` (active memory remains an admitted
optional provider; the selected deployment expresses its obligation through
`*_REQUIRED` flags), `HealthReport` and `memory.health` (bound contract
shapes), `MemorySDK`, the MCP tool inventory (44), the 2.6.0 release.

## C. Consumer handoff (Cursor-Governance; separate from product implementation)

The package now composes every selected capability from settings. What
remains is consumer-owned and must not be placed in the package:

1. **Binding.** `ops/config/memory-binding.json` pins 2.6.0, which does not
   carry this change; 2.6.0 is immutable. Until a later release is admitted
   through the sanctioned ceremony, the full-capability path is reachable
   only through `L9_MEMORY_DEV_CHECKOUT`. Acceptance: `memory-cross-repo`
   workflow green against the bound release, plus `l9-memory readiness`
   reporting the families below.
2. **Runtime configuration in the managed launcher** (`ops/memory/run_memory_mcp.sh`
   and the Hetzner process), credentials through permitted secret sources only:
   `L9_MEMORY_STORE_BACKEND=postgres` with the DSN secret;
   `L9_MEMORY_GRAPH_BACKEND=neo4j`, `L9_MEMORY_GRAPH_REQUIRED=true`, reader
   credential; `L9_MEMORY_ACTIVE_BACKEND=redis`, `L9_MEMORY_ACTIVE_REQUIRED=true`,
   `L9_MEMORY_ACTIVE_DEPLOYMENT_ID`, `L9_MEMORY_ACTIVE_TRUST_DOMAIN`,
   `L9_MEMORY_ACTIVE_ENVIRONMENT=production`, and one of
   `L9_MEMORY_ACTIVE_REDIS_URL_FILE` / `_PASSWORD_FILE` / `_URL_ENV`;
   `GRAPHITI_MCP_URL` and `GRAPHITI_MCP_TOKEN` with either
   `L9_MEMORY_PROJECTION_BACKEND=http` or the manifest runtime
   (`L9_MEMORY_PROJECTION_RUNTIME=manifest`, `L9_MEMORY_PROJECTION_MANIFEST=config/projections/facts-v8.yaml`,
   and `ZEP_API_KEY` for the shadow target). Acceptance: `l9-memory readiness`
   returns `full_capability: true`; `/readyz` 200 with every family
   `selected`, `healthy`, `ready`.
3. **External substrates and credentials.** A Graphiti MCP endpoint reachable
   from the deployment, the model key its extraction needs, and (for the
   shadow target) a Zep subscription. Acceptance per the BLOCKED rows above.
4. **Governance readiness ladder.** `ops/memory` readiness (`R0 … R9`) should
   consume `ReadinessReport` families instead of `memory.health` alone, so
   the governance surface cannot report green while a required family is
   absent. Also repair the environment fault observed at SessionStart:
   `/root/.cursor-governance/.venv` holds package 2.5.0 against an expected
   2.6.0 (`make -C ~/.cursor-governance memory-readiness`).
5. **Drills on the target.** One Redis outage, one Neo4j restart, one
   PostgreSQL restore into an empty store, each followed by
   `l9-memory readiness` COMPLETE, recorded as receipts in Cursor-Governance.
6. **PR #708.** Its text names the same acceptance bar ("aggregate fail-closed
   readiness verdict, outage/recovery and restore evidence"); the product now
   provides the verdict and the executable outage/recovery form. The
   remote-host/Mobile access boundary it marks unresolved stays unresolved
   here: nothing in this change publishes an HTTP memory endpoint.

## E. Phase 5: projection seam matrix

Independent qualification of every projection seam, recorded 2026-10-09 on
the repair branch. Evidence keys add `GM` = the official Graphiti MCP server
(`getzep/graphiti` v0.30.2 checkout, `mcp_server`, HTTP transport at
`127.0.0.1:8800`, Neo4j provider on `N4`, extraction through the OpenRouter
route with `LLM_STRUCTURED_OUTPUT_MODE=json_object`; the model key bound
in-process from Infisical and placed only in the server's environment), and
`CP` = the official-dialect in-process server of
`test_graphiti_http_projection_loop` (composition). The suite is
`tests/integration/test_projection_seams_live.py`: `CP` 10 passed, 1 skipped
(seam 2 needs a live endpoint); `GM` 10 passed, 1 skipped (the outage case
stops only the in-process endpoint) on the final run, after a first run of
8 passed in which seams 4 and 6 exposed the two findings below. No seam
below is green on a mock alone.

| Seam | Handoffs checked | `CP` | `GM` | Status |
|---|---|---|---|---|
| 1. Canonical → Projection | record ACTIVE in PostgreSQL; one durable `memory.record.project` intent per compiled target, PENDING before the worker runs; Graphiti DELIVERED and Zep RETRY→DEAD with the error on the intent, never on the record; link `provider_type=graphiti_mcp`, namespace-bound, episode-name locator (ADR-091); provider copy holds the `facts.render.v3` rendering with `record_id`, `namespace`, `tenant_id`, `schema_version`, provenance, in the `l9g-v1` group; readiness projection family `verified: true` from the live probe, shadow mode never degrading | pass | pass | PASS |
| 2. Graphiti → Neo4j | `Episodic {name: 'memory:<id>', group_id: l9g-v1-<sha256(tenant, namespace)>}` persisted with `MENTIONS` entities and `RELATES_TO` facts citing the episode uuid; the link's locator resolves to that name (the server's `add_memory` returns no uuid); read-only intelligence and GDS over the same scope: `N4` 27/27 (`graph-live`) and `test_canonical_writes_reach_graph_intelligence` | skip (no graph) | pass | PASS (live only, by design) |
| 3. Projection → Retrieval | with the canonical window emptied, a provider hit alone surfaces the record; `matched_by` carries `projection`; evidence names the target, `succeeded`, `contributed=1`; shadow target never queried; principal without READ → `AuthorizationError`; superseded copy withdrawn and excluded, reachable only with `include_superseded` from canonical state; archived copy retired and excluded, reachable only with `include_archived` | pass | pass after repair | PASS |
| 4. Zep shadow | Zep intent retried to `outbox_max_attempts` then DEAD, `attempts` and `last_error` recorded, no Zep link; Graphiti unaffected; baseline retrieval never attempts a shadow store; with `shadow_measurement=True` the hits, order and scores are unchanged and the shadow evidence is `mode=shadow`, `contributed=0`, `succeeded=False` | pass | pass after content repair | PASS for isolation and failure accounting; BLOCKED for live delivery (no Zep subscription; owner: consumer) |
| 5. Lifecycle propagation | deletion answers PENDING_PROJECTION with the record not yet DELETED, one `memory.record.erase` intent per target; the Graphiti copy is gone and the record DELETED only after every held copy is erased (the Zep erase of a never-delivered copy is a verified no-op); `rebuild-projection` re-queues once per target and a repeat re-queues nothing; supersession and archival withdraw the copy (seam 3) | pass | pass | PASS |
| 6. Failure and recovery | provider outage → RETRY with the error, backlog counted, no link; restart of the endpoint and a fresh worker drain the backlog to DELIVERED; a claim abandoned by a dead worker is re-claimed after the lease; an idempotent replay creates no second intent and a second drain re-delivers nothing; a record archived before delivery is never projected and holds no link | pass | pass (outage case is in-process only) | PASS |
| 7. Deterministic reconciliation | expected (canonical ACTIVE records with links) vs observed (provider episodes by name) agree after a drain; rebuild then reconcile is idempotent on repeat | pass | pass | PASS |

### Divergent handoffs found and repaired (package-owned)

1. **Seam 3, `GM`.** The official server's `search_memory_facts` results carry
   `episodes` but no score. `GraphitiProjection._score` mapped the absence to
   `0.0`; the planner hydrated the record from the episode mapping and then
   credited the projection with nothing, so the hit surfaced only when the
   canonical lexical match found it anyway (`matched_by` without
   `projection`; a record with no lexical overlap was dropped). Owner: this
   package. Repair: rank-derived score for unscored hits, as the entity search
   already treats node order (ADR-091 item 5 amended; unit test
   `test_fact_search_scores_unscored_provider_hits_by_rank`).
2. **Seam 4, real client.** `ZepCloudTransport` passed `group_id` to
   `zep-cloud` 3.25, which accepts only `graph_id`; every shadow delivery
   failed in the client before any request. Owner: this package. Repair:
   `graph_id` for `graph.add` and `graph.search`; the fake client now locks
   the keyword.

### Findings routed to their owners (not repaired here)

- **Provider extraction decides reachability.** A record whose content yields
  no entity (`GM` ingested "the deploy window is tuesday afternoon" with zero
  entities and zero facts) is not reachable through the projection: fact
  search cites episodes, node search carries no provenance (ADR-091 item 5,
  disclosed). Canonical retrieval still serves it. Owner: ADR-091 design;
  the seam proves what the contract promises, not more.
- **Acknowledged-then-dropped ingestion upstream.** `GM` answered `queued` for
  "idempotent fact", then its queue rejected the episode
  (`Document.description` null from the extraction model under
  `json_object` mode: a pydantic validation error in `mcp_server`). The outbox
  intent is DELIVERED while no copy exists, which is exactly the
  swallowed-failure semantics ADR-091 item 3 names; reconciliation (seam 7,
  `graph-cutover-status` confirmed count) is the detection path. Owner:
  upstream `getzep/graphiti` `mcp_server` entity types and the deployment's
  model route. Proof request: a confirmed-count check after every deployment
  ingestion batch.
- **Structured-output route.** Through OpenRouter the server fails every
  extraction in `json_schema` mode (`additionalProperties` rejected) and
  works in `json_object` mode. Owner: deployment configuration.
- **Live Zep delivery** stays BLOCKED on a subscription (owner: consumer).

## D. Full-capability verdict

**BLOCKED.** Every selected capability is now either verified on a real,
isolated backend or accounted for with its exact blocker. Nothing is dormant
or silently excluded, and the package no longer reports green while a
required family is absent. The deployment is not READY because:

1. Graphiti MCP delivery is proven against an official server run in this
   sandbox (section E), not against the deployment's endpoint, which is not
   reachable from this session or CI (owner: deployment owner / secrets).
2. Zep shadow delivery is unproven: no subscription key (owner: consumer).
3. PostgreSQL restore and the outage drills have not run on the authorized
   target store (owner: deployment owner).
4. The consumer is bound to 2.6.0, which predates this change; a new release
   admission and consumer rebind are separate, authorized steps.

Package implementation completion is not deployment completion; the matrix
above is the boundary between the two.
