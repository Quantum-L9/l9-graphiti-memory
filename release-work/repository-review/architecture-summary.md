<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/repository-review/architecture-summary.md
layer: repository_review
owner: memory-control-plane
status: active
version: 2.2.0
pinned_sha: 16d5305c0124d85bf06b719c5bac4c516bfe9085
generated: 2026-07-26
generated_by: Manus AI repository review
/L9_META -->

# Architecture Summary

Repository: `Quantum-L9/l9-graphiti-memory` at pinned SHA `16d5305c0124d85bf06b719c5bac4c516bfe9085` (release 2.2.0). Sources: `README.md`, `ARCHITECTURE.md`, `ALIGNMENT.md`, `MANIFEST.md`, `docs/adr/` (62 accepted ADRs), and direct inspection of `src/l9_graphite_memory/`.

## A. Classification

1. The artifact is a **dependency package** with an SDK facade and optional service, provider, hook, and constellation adapters. It is explicitly not a runnable constellation node (`ALIGNMENT.md`, ADR-001).
2. The repository name uses **Graphiti** for the graph-memory integration, while the published distribution and import remain `l9-graphite-memory` / `l9_graphite_memory` for compatibility (ADR-058, `pyproject.toml` name field).
3. The system is a **contract-governed, bi-temporal memory control plane** for autonomous agents: one authorized `MemoryService`, one canonical `RecordStore`, typed evidence receipts, explicit valid-time plus transaction-time coordinates, and rebuildable graph or semantic projections.

## B. Layered structure

| Layer | Owner paths | Responsibility |
|---|---|---|
| Surfaces | `cli.py`, `server.py`, `mcp_tools.py`, `sdk.py`, `hooks/` | CLI (`l9-memory`), remote MCP/HTTP server, canonical `memory.*` MCP tools with legacy aliases, Python SDK, editor hooks |
| Identity and authority | `authz/authenticator.py`, `authz/policy.py` | Server-derived `MemoryPrincipal`; `NamespacePolicy` evaluates read/write/promote/archive/admin claims |
| Control plane | `services/memory_service.py` | The only authorized write and read orchestrator: authorize → normalize → validate → admit → commit → receipt |
| Admission | `admission/normalization.py`, `admission/policy.py`, `admission/engine.py` | Deterministic digests, PII redaction, safety signals, versioned admission decisions, quarantine |
| Contracts | `contracts/` (11 modules), `schema/registry.py`, `schema/upcasters.py` | `MemoryRecord`, receipts, requests, temporal coordinates, privacy/consent, profiles; deterministic schema migration graph |
| Canonical storage | `ports/record_store.py`, `adapters/sqlite_store.py`, `adapters/in_memory_store.py` | RecordStore owns records, status events, receipts, phase locks, outbox events, idempotency mappings, projection links |
| Projections | `ports/projection.py`, `adapters/graphiti_projection.py`, `adapters/null_projection.py`, `transport.py`, `zep_transport.py`, `services/outbox_worker.py` | Optional, rebuildable Graphiti MCP (`http`) or Zep Cloud (`zep`) projections behind a durable outbox; `none` is fully functional |
| Retrieval | `retrieval/query_classifier.py`, `retrieval/planner.py`, `retrieval/ranking.py`, `retrieval/budget.py` | Deterministic intent classification, independent strategy execution, fusion of returned candidates only, explainable ranking, bounded hydration |
| Curation and lifecycle | `curation/promotion.py`, `curation/retention.py`, `curation/procedural.py`, `lineage/replay.py`, `prune.py` | Default-deny promotion, policy retention, review-only procedural synthesis, lineage replay with cycle detection |
| Recovery | `recovery/write_queue.py`, `circuit_breaker.py`, `rate_limiter.py` | Ingress write recovery queue replaying through `MemoryService`; bounded backoff; no direct database emergency path |
| Constellation boundary | `ports/constellation.py`, `integrations/constellation.py` | `GateMemoryBridge` receives an injected canonical TransportPacket factory and Gate client; derives follow-up hops via `derive_or_with_hop`; holds no destination field, peer URL, or node registry (ADR-026, ADR-060) |
| Local guard | `memory_guard.py`, `hooks/` | Expiring hydration and phase-lock receipt verification only; no network I/O, routing, or orchestration (ADR-061) |
| Assurance | `tools/assurance/` (15 gates), `tests/` (34 modules), `validation/` | Executable enforcement of the ADR ledger, wiring, bypass, drift, secrets, quality, manifest, and evidence generation |

## C. Canonical write transaction (ARCHITECTURE.md, verified against `services/memory_service.py`)

1. An adapter establishes a server-derived `MemoryPrincipal`.
2. `NamespacePolicy` evaluates write authority.
3. The normalizer computes original and normalized digests, redacts supported PII, and emits safety signals.
4. Sensitive profile classes verify current purpose-bound consent (ADR-049).
5. `AdmissionEngine` emits a versioned decision (ADR-007).
6. `MemoryService` assigns valid-time and transaction-time coordinates (ADR-004, ADR-029).
7. `RecordStore` atomically persists the record, lifecycle status, receipt, and projection outbox event (ADR-046).
8. `OutboxWorker` projects asynchronously and persists the returned provider locator (ADR-057).

No provider call or direct SQL fallback can bypass the canonical service; `tools/assurance/check_memory_write_bypass.py` enforces this with zero findings recorded in `validation/logs/bypass_check.txt` (ADR-036).

## D. Read and hydration path

1. Requested namespaces are intersected with principal claims — arbitrary remote namespaces are a deliberate security break from v0.2 behavior (`docs/COMPATIBILITY_MATRIX.md`).
2. Canonical retrieval filters tenant, namespace, lifecycle state, valid time, transaction time, class, and confidence.
3. `QueryClassifier` selects deterministic retrieval intent; lexical, temporal, graph, and semantic strategies execute independently.
4. `RetrievalPlanner` fuses only actually returned candidates and records every attempted, succeeded, and failed strategy (ADR-039, ADR-054); no backend failure is represented as zero results.
5. Explainable ranking separates authority, trust, confidence, relevance, importance, and recency (ADR-044); `ContextBudgetAllocator` returns a bounded hydration bundle (ADR-011).

## E. Deletion and erasure

Verified deletion redacts canonical content immediately and completes only after required projection erasure succeeds. Projection writes persist a stable episode locator as a `ProjectionLink`; Graphiti erasure uses `delete_episode`, Zep uses `graph.episode.delete`, and the canonical deletion receipt completes only after provider confirmation (ADR-057).

## F. Failure and recovery posture

Authentication, authorization, admission law, canonical persistence, and audit receipts **fail closed**. Optional projection and extraction failures produce explicit partial or failed receipts (ADR-015). Outbox retries use bounded exponential backoff with a terminal dead state; the ingress recovery queue stores accepted writes only when the canonical service is unavailable and replays through `MemoryService` (ADR-018, ADR-055).

## G. Extension model

Add a store by implementing `RecordStore` and passing the conformance suite (`tests/conformance/test_store_contract.py`); add a projection by implementing `ProjectionAdapter` with stable locators plus search, health, and erasure tests; add ingestion by constructing typed requests into `MemoryService`; add enrichment through idempotent outbox consumers. The architecture forbids adding another memory control plane.

## H. Validation state at the pinned SHA

Local deterministic outcome is **PASS** (20 checks, 103 pytest tests, 62 validated ADRs, 44-decision harvest coverage, 25 preflight gates). Production release remains **BLOCKED_ON_EXTERNAL_VALIDATION** on five external blocker classes tracked as RP-001 through RP-009 (`VALIDATION.md`, `validation/validation_report.yaml`, `docs/ISSUE_INDEX.md`).
