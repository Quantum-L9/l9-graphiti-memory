<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: README.md
layer: repository
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-10-13
/L9_META -->

# L9 Graphiti Memory

Contract-governed, bi-temporal memory for autonomous agents.

Version 2.1 is the recursive convergence release for `Quantum-L9/l9-graphiti-memory`. It preserves valid package, CLI, MCP, and hook surfaces while replacing the old provider-centered internals with one authorized `MemoryService`, one canonical record store, typed evidence receipts, explicit temporal coordinates, and rebuildable graph or semantic projections.

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
- A machine-validated 97-ADR ledger and 51-decision harvest coverage map

## L9 alignment boundary

This repository is a dependency package, not a runnable constellation node. Internal operations use typed memory contracts. L9 inter-node consumers inject the canonical TransportPacket factory and Gate client through `GateMemoryBridge`; the package never defines the shared packet model or resolves destinations. Optional editor hooks use a local receipt guard, not a second Gate. See [`ALIGNMENT.md`](ALIGNMENT.md).

The authoritative product contract is [`product-topology.yaml`](product-topology.yaml): ProductKind `dependency`, archetype `l9.dependency-archetype/semantic-subsystem@1`, consumed by local composition as a consumer-bound artifact. Every release is governed by the global `l9.contract/product-release@1`; [`release-work/product-release-binding.yaml`](release-work/product-release-binding.yaml) is the derived map from that law to this repository's validation and proof entrypoints. See [ADR-094](docs/adr/ADR-094-product-topology-and-release-governance.md).

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

## Agent transport: current code and remote target

| | Status on `main` (package 2.6.0) | Notes |
|---|---|---|
| Local stdio MCP (`l9-memory-server --transport stdio`) | **working, supported** | the transport the managed entry from `l9-memory client cursor install` launches (`python -m l9_graphite_memory.server --transport stdio`) and `client cursor verify` proves (ADR-064) |
| CLI and Python SDK | **working, supported** | unchanged |
| HTTP MCP (`l9-memory-server --transport http`) | **present, not qualified for remote agents** | single JSON `POST /mcp`; static bearer token-to-principal map; no Streamable HTTP conformance, protocol negotiation or `Origin` validation; not equivalent to the signed agent identity door |
| Centrally hosted, authenticated HTTPS Streamable HTTP service for Cursor and Claude Code | **target, not implemented** | decided 2026-10-13; see the ADR-038, ADR-083, ADR-082 and ADR-094 amendments |

Release status (operator statement, 2026-10-13): 2.5 is the current release
and 2.6 is the version to be released and deployed. The table describes the
code on `main`, not a released artifact, and does not say what the 2.6 release
will contain.

The target is one hosted `MemoryService` reached over authenticated HTTPS,
with a per-agent principal established server-side on every request, backed
by a new, empty PostgreSQL canonical store. Nothing on current `main` implements
that target, no consumer is bound to it, and no deployment of it is claimed.
Remote client configuration is a later, consumer-owned campaign;
`config/mcp.json.example` stays the generated stdio entry until code changes
it. Whether a hosted service fits the accepted `dependency` topology is an
open question recorded in ADR-094.

### Basic shared canonical deployment (target)

The basic shared deployment the remote target needs is the canonical store and
nothing else: `store_backend: postgres` against a **new, empty** database, and
`projection_backend`, `graph_intelligence_backend` and
`active_memory_backend` left at `none` (and `projection_runtime` at its
`legacy` default). Redis, Graphiti and Neo4j are not
prerequisites, and the five-family full-capability qualification below is not
a prerequisite either. This greenfield path imports, restores or reuses no
existing ledger, graph, cache or backup; moving an existing ledger is the
separate migration path governed by ADR-072 and ADR-077.

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
   (`846f283`) predate it; 2.5 is the current release and 2.6 is still to be
   released and deployed.
6. Prove recovery and backend outage behavior, including canonical write safety
   if projection or active-memory infrastructure is unavailable.

This defines a deployment qualification target, not an assertion that the
standard package runtime currently composes Redis active-agent sessions or
that its HTTP surface is approved as a remote canonical dependency consumer.
The accepted `product-topology.yaml` and its dependency consumption boundary
remain unchanged. A consumer owns its process, deployment choices and exact
release binding. The generic deployment platform does not own memory behavior.

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
