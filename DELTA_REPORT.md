<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: DELTA_REPORT.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Delta Report

## Functional delta from v2.0 to v2.1

| Area | v2.0 | v2.1 |
|---|---|---|
| harvest proof | prose map | machine-validated 44-decision ledger |
| atomic extraction | contract direction | deterministic and evidence-bound implementations |
| profiles | class separation intent | typed profiles, ingestion, consent tests |
| source distillation | importer foundation | document, repository, session, and provider paths |
| lineage | supersession metadata | replay, cycle, and orphan analysis |
| procedural memory | policy/ADR | candidate synthesis worker with approval boundary |
| write recovery | outbox only | canonical ingress recovery queue plus outbox |
| phase lock | grant/deny receipt | fresh task-signature verification |
| hybrid retrieval | shared projection search risk | independent strategy calls and evidence |
| deletion | canonical tombstone | canonical tombstone plus provider erasure confirmation |
| provider locator | absent | canonical `ProjectionLink` in memory and SQLite stores |
| Graphiti tools | older names | current and legacy dialect negotiation |
| Zep deletion | absent | `graph.episode.delete` adapter |
| secret validation | policy | executable scanner |
| SLO validation | policy | executable local benchmark |
| tests | 63 in original v2 release report | 97 in converged release |
| ADRs | 47 | 58 |
| preflight gates | 18 in original v2 release report | 21 |

## Data model delta

SQLite schema version increased from 3 to 4 with an additive `projection_links` table. Canonical record and receipt tables remain compatible.

## Public surface delta

New CLI and MCP operations are additive. Existing names remain. Provider-native Graphiti tool handling is isolated inside the projection adapter and does not change canonical local tools.

## Release delta

The release bundle now includes recursive audit, improvement, delta, convergence, structured validation, and machine-readable harvest evidence.

## Functional delta from v2.1 to v2.2

| Area | v2.1 | v2.2 |
|---|---|---|
| constellation boundary | documented only | injected Gate-only bridge with immutable lineage tests |
| local mutation control | stateful component described as Gate | typed expiring receipt guard |
| file provenance | absent | inline and manifest-carried L9_META |
| alignment validation | indirect | dedicated ten-pass recursive assurance gate |
| layer ownership | documented | AST-enforced dependency direction |
