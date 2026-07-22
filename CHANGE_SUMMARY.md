<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: CHANGE_SUMMARY.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Change Summary

## Release

`2.2.0` recursive convergence and harvest-closure release.

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
