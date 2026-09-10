<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: CHANGE_SUMMARY.md
layer: repository
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-09-06
/L9_META -->

# Change Summary

## Release

`2.3.0` consumer control-plane conformance release (campaign stages M1 and M2 of the Cursor-Governance memory realignment, ADR-082). `2.2.0` was the recursive convergence and harvest-closure release.

## Added

- Evidence-bound atomic extraction and offline distillation
- Identity, preference, behavior, session, and domain profile contracts
- Purpose-bound consent and verified deletion
- Persistent projection links with stable provider locators
- Graphiti `delete_episode` and Zep `graph.episode.delete` erasure paths
- Current Graphiti MCP dialect negotiation for `add_memory` and `search_memory_facts`
- Lineage replay, cycle detection, and orphan reporting
- Procedural synthesis candidates with approval boundary
- Checkpoint integrity utility without checkpoint ownership
- Canonical ingress recovery queue
- Strategy-specific hybrid retrieval receipts
- Secret scanning and local SLO benchmark
- Machine-readable 44-decision harvest coverage ledger
- Recursive improvement, delta, and convergence evidence

## Corrected

- Closed every prior `partial` or `deferred` in-scope harvest item
- Removed false provider-erasure completion claims
- Reconciled provider tool naming with current and legacy Graphiti MCP surfaces
- Updated docs and roadmap to match executable behavior
- Extended SQLite schema to persist projection links

## Preserved

- Distribution name `l9-graphite-memory`
- Import package `l9_graphite_memory`
- CLI and MCP entrypoints
- Legacy MCP aliases
- Hook output shape
- Explicit projection choice and no silent fallback

## External blockers

Live provider, hosted CI, production migration, rollback, and credential-rotation proof remain external gates and are not represented as local passes.

## 2.2.0 recursive alignment

- Added injected TransportPacket and Gate boundary protocols.
- Added immutable Gate-only root and follow-up dispatch.
- Reclassified the local hook component as a receipt guard.
- Added L9_META coverage, manifest v2, layer checks, and recursive alignment enforcement.
- Removed deprecated transport references, camel-case hook aliases, print calls, and generated caches.

## 2.3.0 — consumer control-plane conformance (ADR-082, campaign M1 + M2)

### M1 — transport parity

- Added `l9-memory close` with exit-code verdicts (`0` committed, `3` dry run, `2` failed)
- Added `CloseRequest.idempotency_key` and `CloseReceipt.replayed`: a replayed close yields one logical close
- Added `l9-memory capabilities`, `memory.capabilities`, and `HealthReport.contract_version` (`memory-control-plane/v1`)
- Added `MemorySDK.write_governed`, `ingest_governed_candidate`, `conflicts`, `verify_phase_lock`, `close`, `health`
- Extended the governed-candidate contract: `session_continuation` class, `namespace_local` visibility, lossless `structured_payload`

### M2 — consumer conformance hardening

- Added a tag selector to `MemorySearchRequest` and `HydrationRequest` (`--tag` on `l9-memory search` / `hydrate`, `tags` on `memory.search` / `memory.hydrate`): every requested tag must be present, and a tag match admits a record regardless of query-text relevance. A consumer selects its typed `session_continuation` records with it instead of guessing at content
- `l9-memory client cursor verify --path` now launches the managed entry as written in that file (`ProbeReceipt.argv_source = "installed"`, `config_path`); the default path is probed the same way when it already carries the entry, and only a machine with no config falls back to the generated entry. An entry existing on disk was never proof; now the receipt says what was proven
- Added `probe_installed_entry` to `client_config`
- Added the installed-wheel lifecycle test (`tests/integration/test_installed_wheel_lifecycle.py`): capabilities, health, continuation admission and replay, tag-selected hydrate and search, dry-run and idempotent close, and `client cursor install` + `verify --path`, all from a wheel installed into an empty target with nothing else importable
- Added consumer conformance coverage (`tests/unit/test_consumer_conformance.py`): candidate rejection and quarantine as visible verdicts, authorized and refused read fan-in, canonical operations with `projection=none` and with a failing projection, stale / wrong-task / wrong-namespace phase locks, and the same lifecycle over MCP
- Added the cross-surface fixture `tests/fixtures/control_plane/continuation_candidate.json`, consumed verbatim by Cursor-Governance's cross-repo lifecycle test
- Added `tests/regression/test_release_version_consistency.py`: `pyproject.toml`, `version.py`, the assurance stampers, and the evidence pins must name one release
- Release `2.3.0` is `MEMORY_TARGET_VERSION` for the Cursor-Governance binding (`ops/config/memory-binding.json` there pins it); tag `v2.3.0` on the merge commit

## 2.3.1 — PyPI metadata (no direct URL extra)

`v2.3.0` built and validated but PyPI rejected the upload: the `constellation` extra declared `constellation-node-sdk` as a git URL, which becomes `Requires-Dist` and is a 400 (`Can't have direct dependency`). The extra is removed from published metadata. CI/dev still install Gate_SDK via a uv `dependency-groups.constellation` entry and `[tool.uv.sources]`. Tag `v2.3.0` stays immutable; this patch is the first uploadable release.
