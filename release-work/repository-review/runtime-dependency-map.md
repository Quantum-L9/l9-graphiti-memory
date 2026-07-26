<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/repository-review/runtime-dependency-map.md
layer: repository_review
owner: memory-control-plane
status: active
version: 2.2.0
pinned_sha: 16d5305c0124d85bf06b719c5bac4c516bfe9085
generated: 2026-07-26
generated_by: Manus AI repository review
/L9_META -->

# Runtime Dependency Map

This map records the runtime dependency surface of `l9-graphite-memory` 2.2.0 at pinned SHA `16d5305c0124d85bf06b719c5bac4c516bfe9085`, derived from `pyproject.toml`, `config/memory.yaml.example`, `src/l9_graphite_memory/`, and the compatibility matrix.

## A. Python package dependencies (`pyproject.toml`)

| Scope | Dependency | Constraint | Runtime role |
|---|---|---|---|
| Core (required) | `pydantic` | `>=2.7,<3` | Typed contracts for records, receipts, requests, temporal coordinates, privacy, profiles |
| Core (required) | `pyyaml` | `>=6,<7` | Configuration and packaged resource loading (`defaults.yaml`, `memory_contract.yaml`, `group_registry.yaml`) |
| Extra `server` | `fastapi`, `uvicorn` | per pyproject | Remote MCP/HTTP surface (`l9-memory-server`); optional — core package runs without it |
| Extra `zep` | `zep-cloud` | `>=3,<4` | Zep Cloud projection transport (`zep_transport.py`); loaded only when `projection_backend: zep` |
| Extra `infisical` | `infisical-python` | `>=2,<3` | Optional secret-manager integration behind `secrets.py`; environment variables remain supported |
| Extra `dev` | `build`, `mypy`, `pytest`, `pytest-cov`, `ruff` | per pyproject | Assurance and packaging only; never imported by production modules |

The Python floor is `>=3.10`. SQLite persistence uses the standard-library `sqlite3` module, so the default deployment (`projection_backend: none`) requires only `pydantic` and `pyyaml` beyond the interpreter.

## B. Process entry points

| Entry point | Module | Runtime dependencies beyond core |
|---|---|---|
| `l9-memory` (CLI, 24 commands) | `l9_graphite_memory.cli:main` | none required; projection extras only if configured |
| `l9-memory-server` | `l9_graphite_memory.server:main` | `server` extra (FastAPI, uvicorn); enforces `http_auth_required: true` by default |
| `l9-memory-worker` | `l9_graphite_memory.services.outbox_worker:main` | projection backend transport for the configured provider |

## C. Internal runtime dependency flow (imports verified in source)

Surfaces (`cli.py`, `server.py`, `mcp_tools.py`, `sdk.py`) depend on `services/memory_service.py`, never on stores or providers directly. `MemoryService` depends on `authz/` for principal and namespace evaluation, `admission/` for normalization and versioned admission decisions, `contracts/` plus `schema/registry.py` for typed records and upcasting, and the `ports/record_store.py` abstraction for persistence. `services/outbox_worker.py` depends on `ports/projection.py` and the adapter factory, which selects `graphiti_projection.py` (HTTP transport with dialect negotiation) or `zep_transport.py` or `null_projection.py`. `recovery/write_queue.py` depends on `MemoryService` for replay — it never touches the store directly. `integrations/constellation.py` (`GateMemoryBridge`) depends only on injected constructors: the canonical TransportPacket factory and Gate client are supplied by the host application and are never imported from this package (ADR-026). `memory_guard.py` and `hooks/` depend on local receipt state only, with no network I/O (ADR-061).

## D. External service dependencies (all optional, all behind ports)

| Service | Trigger | Transport | Failure posture |
|---|---|---|---|
| Graphiti MCP server | `projection_backend: http` | `transport.py`, HTTP; prefers `add_memory`/`search_memory_facts`, supports legacy `add_episode`/`search_facts` dialects | Outbox retries with bounded exponential backoff (base 5 s, max 8 attempts) to terminal dead state; canonical write already durable |
| Zep Cloud | `projection_backend: zep` | `zep_transport.py` via `zep-cloud` SDK | Same outbox posture; erasure via `graph.episode.delete` |
| Constellation Gate | Host injects Gate client into `GateMemoryBridge` | Injected client; follow-up hops derived with `derive_or_with_hop`; no peer routing (ADR-060) | Bridge holds no destinations; failures surface to host |
| Infisical | `infisical` extra configured | `secrets.py` boundary | Falls back to environment variables; no plaintext secret persistence (ADR-016) |
| LLM extraction provider | extraction/distillation requests | `extraction/` with typed failure semantics (ADR-041) | Typed failed receipts; core commit never blocked (ADR-046) |

## E. Filesystem and state dependencies

Default paths from `config/memory.yaml.example`: canonical data in `~/.local/share/l9-memory` (SQLite), operational state in `~/.local/state/l9-memory`. Gate/guard hook state moved from the legacy `~/.cursor/graphiti-state` location to the new state directory with legacy read compatibility preserved. Generated MCP client configs contain no tokens; `config_writer` outputs are drift-checked by `tools/assurance/check_config_drift.py`.

## F. Dependency invariants

The default profile (`projection_backend: none`, `projection_required: false`) is fully functional with zero network dependencies — this is the documented and tested baseline. No module outside `adapters/` and the two transport modules may import provider SDKs; `tools/assurance/audit_package_wiring.py` (86 modules, zero unexplained orphans) and `check_layer_boundaries.py` enforce the layering. External-facing runtime proof against live Graphiti and Zep endpoints remains open as RP-004 and RP-005 in `docs/ISSUE_INDEX.md`.
