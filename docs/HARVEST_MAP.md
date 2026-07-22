<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/HARVEST_MAP.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Harvest Map

The rewrite is a controlled synthesis. Source packs contribute concepts and failure knowledge, not authority over the final dependency graph.

| Source | Harvested and implemented | Explicitly rejected |
|---|---|---|
| `L9-Graphite-Memory-reconciled` | transport abstraction, Zep and Graphiti adapters, Infisical loading, gates, CLI and MCP compatibility, package workflows | stale paths, plaintext config secrets, duplicated tool contracts, silent fallback |
| `L9-Graphite-Memory-full-commit-pack` | negative regression fixtures and retired-deployment evidence | implicit localhost fallback, old VPS architecture, weaker tests |
| `L9_Graphiti_Handoff_Deliverables` | managed-backend decision history and migration success criteria | sacred-file doctrine, system-wide install assumptions, rollback to broken provider paths |
| `l9-graphiti-commit-pack` | admission, hydration, context budgets, provenance, authority policy, session ingestion, idempotent orchestration | duplicate L9-Ops-MCP memory server and direct Graphiti singleton |
| `Memory Packs` | taxonomy, confidence/evidence, atomic units, profile isolation, promotion lifecycle, decay, hybrid retrieval, source traceability | synthetic pass-only validation and broad cognitive-runtime scope |
| `L9 Repo memory` | normalization, hashing, temporal history, governance context, retention, lineage, recovery, checkpoint integrity | god service, mandatory multi-database stack, world-model and agent-checkpoint ownership |
| `cryptoxdog/L9_Original_Repo` | schema registry, bypass scanner, config authority, protocol boundaries, invariant tests, SDK-first lessons, importance factors, procedural candidates, distillation | deprecated universal-envelope law, giant DAG, route sprawl, environment-skipped proof |
| Recursive audit of v2 pack | harvest coverage ledger, provider locator persistence, Graphiti dialect negotiation, verified Graphiti/Zep deletion, local SLO and secret gates | unproved live-provider and production-readiness claims |

## Closure law

Every promised concept is listed in `docs/harvest_coverage.yaml` as exactly one of:

- `implemented`: existing implementation, tests, and ADRs
- `rejected_boundary`: explicit scope rejection with an ADR
- `blocked_external`: implementation exists or the gate is defined, but proof requires credentials, hosted CI, or a production-like environment

`tools/assurance/validate_harvest_coverage.py` fails when an implemented item lacks code, tests, or ADR evidence, when a boundary rejection lacks rationale, or when a blocker is unnamed.
