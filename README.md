<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: README.md
layer: repository
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-07-27
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
- A machine-validated 69-ADR ledger and 44-decision harvest coverage map

## L9 alignment boundary

This repository is a dependency package, not a runnable constellation node. Internal operations use typed memory contracts. L9 inter-node consumers inject the canonical TransportPacket factory and Gate client through `GateMemoryBridge`; the package never defines the shared packet model or resolves destinations. Optional editor hooks use a local receipt guard, not a second Gate. See [`ALIGNMENT.md`](ALIGNMENT.md).

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

## Validation

```bash
pytest -q
python tools/assurance/validate_harvest_coverage.py
python tools/assurance/validate_adrs.py
bash scripts/preflight.sh
bash scripts/validate_release.sh
```

`validate_release.sh` builds and installs the wheel, runs installed-package smoke checks, and writes evidence under `validation/`. Live provider, production migration, hosted CodeQL, branch-protection, and credential-rotation proofs remain external release gates.

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
- [Full ADR ledger](docs/adr/README.md)
- [Agent skill](skill/SKILL.md)
- [Validation evidence](VALIDATION.md)
