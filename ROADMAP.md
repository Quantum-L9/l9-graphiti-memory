<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: ROADMAP.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Roadmap

## v2.2 recursive convergence gates

Implemented and locally validated:

- canonical contracts, service, stores, and typed receipts
- consent-governed profiles and verified deletion
- atomic extraction, source distillation, and session adapters
- independent retrieval strategies and bounded hydration
- promotion, retention, lineage, phase-lock verification, and procedural candidates
- schema upcasting, write-bypass detection, configuration drift detection, wiring audit, secret scan, and local SLO benchmark
- provider locator persistence and provider erasure adapters
- wheel build, installed-wheel smoke, ADR validation, and harvest coverage validation

External release gates are tracked by the remaining-proof issue pack:

1. `RP-001`: authoritative TransportPacket integration
2. `RP-002`: production Gate client and receipt integration
3. `RP-003`: credentialed Gate staging lifecycle
4. `RP-004`: live Graphiti lifecycle and replay
5. `RP-005`: live Zep lifecycle and replay
6. `RP-006`: production-like migration and rollback
7. `RP-007`: hosted CI, security scanning, and release governance
8. `RP-008`: external secret lifecycle proof
9. `RP-009`: consolidated production release decision

The authoritative rationale and evidence contract are in `docs/REMAINING_PRODUCTION_PROOF.md`.

## Post-v2.2 candidates

Candidates must prove measured need and preserve the existing contracts:

1. PostgreSQL `RecordStore` with transaction-scoped RLS
2. Encrypted local `RecordStore`
3. Projection rebuild and reconciliation command with provider inventory diff
4. Optional query rewriting and neural reranking with evidence-bearing receipts
5. Multi-projection fan-out with per-provider lifecycle state
6. Signed cross-runtime receipts using the canonical constellation transport owner

No candidate enters core based on novelty or folder neatness.
