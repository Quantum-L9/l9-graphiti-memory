<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: README.md
layer: repository
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-10-14
/L9_META -->

# L9 Graphiti Memory

Contract-governed, bi-temporal memory for autonomous agents.

Version 2.1 was the recursive convergence release for `Quantum-L9/l9-graphiti-memory`. It preserves valid package, CLI, MCP, and hook surfaces while replacing the old provider-centered internals with one authorized `MemoryService`, one canonical record store, typed evidence receipts, explicit temporal coordinates, and rebuildable graph or semantic projections.

The repository name uses **Graphiti** because the project integrates with Graphiti-style graph memory. The published distribution and Python import remain `l9-graphite-memory` and `l9_graphite_memory` for compatibility. See ADR-058.

## Guarantees

- One canonical durable write path
- Server-derived principals and namespace authorization
- Versioned memory taxonomy and schema upcasting
- Valid-time plus transaction-time queries
- Deterministic admission, quarantine, idempotency, and supersession
- Evidence-bound atomic extraction and offline source distillation
- Consent-governed identity and preference memory
- Bounded hydration with explainable ranking
- Independent graph, semantic, lexical, and temporal retrieval evidence
- Atomic core commit plus durable projection outbox
- Persistent provider locators for verified projection erasure
- Governed promotion, retention, lineage replay, and procedural candidates
- Explicit complete, partial, failed, duplicate, rejected, quarantined, archived, and deleted outcomes
- No plaintext secret persistence in generated agent configuration
- Installed-wheel operation without a source checkout
- A machine-validated ADR ledger (`docs/adr/`) and 51-decision harvest coverage map

## L9 alignment boundary

This repository is a dependency package, not a runnable constellation node; from 3.0.0 it may also run as one centrally hosted Memory service under an admitted product-kind exception, still without Constellation identity or Gate routing. Internal operations use typed memory contracts. L9 inter-node consumers inject the canonical TransportPacket factory and Gate client through `GateMemoryBridge`; the package never defines the shared packet model or resolves destinations. Optional editor hooks use a local receipt guard, not a second Gate. See [`ALIGNMENT.md`](ALIGNMENT.md).

The authoritative product contract is [`product-topology.yaml`](product-topology.yaml): ProductKind `dependency`, archetype `l9.dependency-archetype/semantic-subsystem@1`, claiming the admitted exception `l9.product-kind-exception/memory-hosted-service@1` (Semantic Foundation v3.21.0): canonical consumption is remote invocation over authenticated MCP Streamable HTTP of one independently running service, and the wheel and sdist remain the release artifacts. Every release is governed by the global `l9.contract/product-release@1`; [`release-work/product-release-binding.yaml`](release-work/product-release-binding.yaml) is the derived map from that law to this repository's validation and proof entrypoints. See [ADR-094](docs/adr/ADR-094-product-topology-and-release-governance.md).

## Architecture

```text
CLI / MCP / Python SDK / compatibility hooks
                    |
           authenticated principal
                    |
               MemoryService
  authorize -> normalize -> validate -> admit -> commit -> receipt
                                      |
                         canonical RecordStore
                                      |
                       atomic durable outbox
                                      |
                    optional projections
                 Graphiti MCP / Zep / none
```

The canonical SQLite store is fully functional without Zep, Neo4j, PostgreSQL, Redis, LangGraph, or an LLM. Optional providers are projections, not sources of truth.

## Install

Checkout-based development uses **uv** with the committed lockfile (ADR-069):

```bash
# https://docs.astral.sh/uv/getting-started/installation/
uv sync --frozen --no-install-project --no-build --extra dev --extra server
source .venv/bin/activate   # or prefix commands with: uv run
```

Or: `bash scripts/install.sh` (requires `uv`).

Published distribution consumers (no checkout) may still use pip:

```bash
python -m pip install l9-graphite-memory
python -m pip install 'l9-graphite-memory[server,zep]'
```

## Quick start

```bash
export L9_MEMORY_PROJECTION_BACKEND=none
l9-memory resolve
l9-memory health
l9-memory write 'Always run contract tests before merge' \
  --kind decision \
  --group-id l9-graphiti-memory \
  --source operator
l9-memory search 'contract tests' --group-id l9-graphiti-memory
```

Sensitive profile writes require purpose-bound consent evidence. Verified deletion requires administrator authority, a reason, and a verification reference.

## Command surface

```text
health, resolve, write, search, hydrate, get, stats, conflicts,
phase-lock, verify-phase-lock, lineage, bootstrap, import, distill,
inject, autoseed-check, prune, promote, delete,
synthesize-procedures, maintain, rebuild-projection, outbox-run,
drain-legacy-write-queue, ingest-topology-plan
```

Legacy MCP aliases `write`, `search`, `health`, `bootstrap`, `phase_lock`, and `conflicts` remain thin adapters to canonical `memory.*` handlers.

## Configuration

Copy `config/memory.yaml.example` and set `L9_MEMORY_CONFIG` to its path. Environment variables override YAML. Cursor and Claude config writers persist commands and non-secret settings only. Cursor instantiation is governed by the canonical `l9-memory client cursor` lifecycle (`inspect`, `install`, `verify`, `status`, `uninstall`); see `docs/CURSOR_INSTANTIATION.md` and ADR-064.

Canonical store choices:

- `sqlite` (default): a single-process local ledger. Not a distributed authority — only processes that can open the file share the memory.
- `postgres`: the shared backend for multi-agent and scheduled deployments. Requires `L9_MEMORY_POSTGRES_DSN` and the `postgres` extra (`pip install 'l9-graphite-memory[postgres]'`). See ADR-072.

Projection choices:

- `none`: canonical standalone memory only
- `http`: official or legacy Graphiti MCP projection
- `zep`: Zep Cloud graph projection through `zep-cloud`

The HTTP adapter discovers the live Graphiti tool inventory. It supports the current `add_memory`, `search_memory_facts`, `search_nodes`, and `delete_episode` dialect plus the older `add_episode` and `search_facts` compatibility dialect.

## Release and transport status

Five states are kept apart throughout this repository. "Implemented",
"supported", "verified", "released" and "deployed" are not interchangeable.

| State | Identity (2026-10-14; `main` and Target rows 2026-11-13) | Agent transport |
|---|---|---|
| Current operational release | **2.5.0** (operator-designated) | local stdio MCP |
| Package release line | **2.6.0**: `v2.6.0` tag and a published 2.6.0 artifact (`846f283`) exist; not designated the operational release | local stdio MCP; HTTP present but not a conforming Streamable HTTP server and authenticated only by static bearer tokens |
| `main` | source version **3.0.0** (`pyproject.toml`, `src/l9_graphite_memory/version.py`; observed at `ae6e2c0`). No `v3.0.0` tag, no 3.0.0 admission receipt under `docs/receipts/`, no 3.0.0 artifact on PyPI; not an admitted release | stateless Streamable HTTP (`2025-11-25`, `2025-06-18`, ADR-098) with `bearer` (default) and `signed-agent` modes; neither mode is a hosted door (ADR-100) and there is no OAuth mode yet (issue #108); stdio unchanged (`2024-11-05`) |
| Target | **Memory 3.0.0**: first live release of the consolidated remote architecture | one hosted `MemoryService` over native MCP Streamable HTTP protected by Auth0 OAuth (ADR-100) |
| Qualified deployment | **none** | no C1 deployment exists or is claimed |

Memory 3.0.0 is bound to exact source and built-artifact identities only by a
merged admission receipt for those exact bytes (ADR-022, ADR-094); none exists
for 3.0.0. A Git tag, a published package, a
deployment and operator acceptance are separate facts. The TypeScript client's
package version 3.0.0 is an npm version, not Memory 3.0.0.

### Memory 3.0.0 target architecture

```text
Cursor agent(s) ──────┐
                      │
Claude Code agent(s) ─┼── OAuth-protected HTTPS MCP (Streamable HTTP)
                      │              │
Other authorized ─────┘              ▼
agents                     Hetzner C1 hosting boundary (TLS reverse proxy)
                                         │
                                  Memory HTTP adapter
                                         │
                                 one MemoryService
                                         │
                              new, empty PostgreSQL store
```

- One logical `MemoryService`, intended to be centrally hosted on the
  operator-controlled Hetzner C1 environment. Agents on different machines
  will consume it; they are consumers, not canonical memory servers. The
  runtime will not depend on the operator's Mac.
- The hosted credential is an Auth0 access token bound to the one Memory
  resource; signed-agent HMAC, static bearer and Memory stdio are not hosted
  doors and are not fallbacks (ADR-100, which supersedes the hosted
  provisions of ADR-083 and ADR-098). A verified OAuth principal is not an
  actor or a surface, and consequential actor attribution fails closed when
  the actor is unproved. Shared storage does not imply shared authorization:
  tenant and namespace authorization are enforced independently by
  `MemoryService`.
- HTTP is an adapter. No second memory API, gateway, authorization server or
  `MemoryService` is introduced. The CLI stays the operator interface and the
  SDK stays supported. The stdio, signed-agent and bearer code paths are
  still in the tree as legacy code until a later change removes them; they
  are not the hosted contract (ADR-100).
- Hostname, address, certificate, process supervisor and operating-system
  configuration are unverified until deployment evidence exists.

What stands between `main` and a live 3.0.0: the OAuth resource server, which
this source does not have (`http_auth_mode` admits only `bearer` and
`signed-agent`), and the live PKCE receipt ADR-100 requires before it is
treated as proven; until then the hosted carrier image refuses every auth mode
and does not start (`Dockerfile`, `.l9/deployment.yaml`, issue #108). Also:
release validation on exact bytes; the protocol suite and receipt shapes on PostgreSQL
(cross-process sharing on PostgreSQL is proven, under signed-agent identity, by
`tests/integration/test_remote_mcp_postgres_multiprocess.py`); release and service admission (the product classification is settled by ADR-094, 2026-10-15); C1
deployment evidence; and consumer adoption, which each consumer owns.
Cursor-Governance currently seals the agent HTTP path, so the Cursor and
Claude Code agents it governs need an authorized consumer campaign first. `config/mcp.json.example` stays the
generated stdio entry.

### Basic shared canonical deployment (target)

The basic shared deployment the remote target needs is the canonical store and
nothing else: `store_backend: postgres` against a **new, empty** database, and
`projection_backend`, `graph_intelligence_backend` and
`active_memory_backend` left at `none` (and `projection_runtime` at its
`legacy` default). The server must be installed with the `postgres` extra
(`l9-graphite-memory[server,postgres]`). Redis, Graphiti and Neo4j are not
prerequisites, and the five-family full-capability qualification below is not
a prerequisite either; a healthy PostgreSQL `canonical` family is not evidence
that any optional family is healthy. This greenfield path imports, restores or
reuses no existing ledger, graph, cache or backup; moving an existing ledger
is the separate migration path governed by ADR-072 and ADR-077, and none is
initiated.

## Consumer-selected full-capability shared deployment

The installable `l9-graphite-memory` product remains a locally composed L9
Dependency. Individual consumers may select a stricter deployment profile
without making PostgreSQL, Redis or Graphiti mandatory for all installations.

A consumer choosing the full-capability shared-agent deployment MUST:

1. Use one PostgreSQL canonical record store. Every memory read and write flows
   through `MemoryService`; projections are never canonical. The two lawful
   paths to that store are distinct and are never collapsed:
   - **Greenfield** (the selected fresh full-capability staging deployment):
     provision a brand-new, empty PostgreSQL canonical database. No prior
     SQLite ledger, PostgreSQL database, Graphiti/Neo4j graph, Redis state,
     backup, transcript or other existing memory is imported, restored,
     merged or reused, and no historical reconciliation or migration runs.
   - **Migration** (only for a consumer that separately chooses to move an
     existing canonical ledger): ADR-072 and ADR-077 govern the explicit
     transition acknowledgement and migration boundary. This section neither
     changes that law nor authorizes any data move.
2. Enable and qualify the Graphiti projection/outbox and the separate Neo4j
   graph-intelligence reader using real backends and the existing product tools.
3. Meet `docs/ACTIVE_MEMORY_DEPLOYMENT_CONTRACT.md` for Redis and prove both
   Redis active-store and actual Redis awareness-bus behavior. An installed
   `ActiveAgentClient` symbol is not proof an agent consumer can use it.
4. Bind every process to the intended tenant, namespace authorization and
   backend identity using product-supported runtime configuration. Never store
   credentials in tracked deployment files or generated MCP settings.
5. Report the five capability families independently, each on its own
   evidence: `canonical`, `projection`, `graph`, `active_store` and
   `awareness_bus`. The full-capability verdict is `full_capability=true`:
   every family selected and healthy over the shared PostgreSQL canonical
   store. A SQLite canonical store, a shadow-only projection or an incomplete
   Redis capability probe never yields it. An HTTP
   200 from `/healthz` or `/readyz` alone is not full-capability proof:
   `/readyz` answers the aggregate `ready` verdict over required families,
   which is weaker than `full_capability`. The five-family readiness report
   is on `main` (ADR-097, merged through PR #91) and must be proven in the
   final combined candidate. The `v2.6.0` tag and the 2.6.0 artifact on PyPI
   (`846f283`) predate it. For release identities see "Release and transport
   status" above.
6. Prove recovery and backend outage behavior, including canonical write safety
   if projection or active-memory infrastructure is unavailable.

This defines a deployment qualification target, not an assertion that the
standard package runtime currently composes Redis active-agent sessions or
that any deployment of its HTTP surface is admitted. The topology permits
authenticated remote canonical consumption under the admitted exception
(ADR-094, 2026-10-15), but release admission, service admission and deployment
remain separate decisions. A consumer owns its own binding to an exact release. The generic deployment platform does not own memory behavior.

## Validation

```bash
pytest -q
python tools/assurance/validate_harvest_coverage.py
python tools/assurance/validate_adrs.py
bash scripts/preflight.sh
bash scripts/validate_release.sh
```

`validate_release.sh` builds and installs the wheel, runs installed-package smoke checks, and writes evidence to the untracked `build/release-validation/` workspace (override with `L9_RELEASE_EVIDENCE_DIR`); it never writes the tracked `validation/` tree. Live provider, production migration, hosted CodeQL, branch-protection, and credential-rotation proofs remain external release gates.

## Documentation

- [Architecture](ARCHITECTURE.md)
- [Runbook](RUNBOOK.md)
- [Migration](MIGRATION.md)
- [Security](SECURITY.md)
- [Recursive harvest audit](docs/RECURSIVE_HARVEST_AUDIT.md)
- [Machine-readable harvest coverage](docs/harvest_coverage.yaml)
- [Harvest map](docs/HARVEST_MAP.md)
- [Remediation and integration register](docs/REMEDIATION_AND_INTEGRATION_PLAN.md)
- [Compatibility matrix](docs/COMPATIBILITY_MATRIX.md)
- [Topology publication admission](docs/TOPOLOGY_PUBLICATION_ADMISSION.md)
- [Product topology](product-topology.yaml) and [release binding](release-work/product-release-binding.yaml)
- [Full ADR ledger](docs/adr/README.md)
- [Agent skill](skill/SKILL.md)
- [Validation evidence](VALIDATION.md)
