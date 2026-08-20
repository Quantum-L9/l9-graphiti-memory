<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: ARCHITECTURE.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Architecture

## System identity

`l9-graphiti-memory` is a dependency package with embedded operator and protocol adapters. It owns governed memory contracts, canonical persistence, retrieval planning, curation controls, and projection integration. It does not own agent execution, a world model, reasoning orchestration, constellation routing, or full agent checkpoint persistence.

## Control flow

```text
                     +------------------+
                     | Python SDK       |
                     +--------+---------+
                              |
+--------+  +------+  +-------v------+  +------------------+
|  CLI   |  | MCP  |  | importers    |  | compatibility    |
+---+----+  +--+---+  +-------+------+  | hooks            |
    |          |              |         +---------+--------+
    +----------+--------------+-------------------+
                              |
                     +--------v---------+
                     | MemoryPrincipal  |
                     +--------+---------+
                              |
                     +--------v---------+
                     | MemoryService    |
                     +------------------+
                     | authorize        |
                     | normalize/redact |
                     | validate/upcast  |
                     | consent/admit    |
                     | idempotency      |
                     | atomic commit    |
                     | typed receipt    |
                     +---+----------+---+
                         |          |
            +------------v--+   +---v----------------+
            | RecordStore   |   | durable outbox     |
            | canonical     |   +---+----------------+
            +---------------+       |
                            +-------v------------------+
                            | optional projections     |
                            | Graphiti MCP / Zep / none|
                            +--------------------------+
```

## L9 constellation boundary

`MemoryRecord`, requests, and receipts are internal domain contracts. When memory intent crosses an L9 node boundary, `GateMemoryBridge` receives the canonical TransportPacket factory and Gate client from their owning packages. It creates root packets or derives follow-up hops through `derive_or_with_hop`, verifies trace and lineage preservation, and dispatches only to Gate. The bridge contains no destination field, peer URL, or node registry.

Provider calls to Graphiti or Zep are projection I/O, not node-to-node routing. They remain adapter-local and cannot invoke another L9 node.

## Local receipt guard

Optional editor hooks use `memory_guard.py` to verify an expiring hydration and phase-lock evidence cache. The guard is not constellation Gate: it performs no network I/O, routing, admission, or workflow orchestration. Historical gate-named files are compatibility wrappers only.

## Canonical state

`RecordStore` owns:

- `MemoryRecord`
- `MemoryStatusEvent`
- operation receipts
- phase-lock receipts
- outbox events
- idempotency mappings
- projection links containing stable provider locators

Graph and semantic providers are rebuildable projections. They may improve retrieval, but they cannot create canonical records, grant authority, or define lifecycle state.

## Write transaction

1. An adapter establishes a server-derived `MemoryPrincipal`.
2. `NamespacePolicy` evaluates write authority.
3. The normalizer computes original and normalized digests, redacts supported PII, and emits safety signals.
4. Sensitive profile classes verify current purpose-bound consent.
5. `AdmissionEngine` emits a versioned decision.
6. `MemoryService` assigns valid-time and transaction-time coordinates.
7. `RecordStore` atomically persists the record, lifecycle status, receipt, and projection outbox event.
8. `OutboxWorker` projects asynchronously and persists the returned provider locator.

No provider call or direct SQL fallback can bypass the canonical service.

## Extraction and source ingestion

Atomic extraction converts source material into independently governed assertions with exact source ranges and source digests. Offline distillation can ingest documents, repositories, or session material through the same write path. Provider-backed extraction is optional and must return typed evidence, status, model metadata, and token-budget information.

## Read and hydration

1. Requested namespaces are intersected with principal claims.
2. Canonical retrieval filters tenant, namespace, lifecycle state, valid time, transaction time, class, and confidence.
3. `QueryClassifier` selects deterministic retrieval intent.
4. Canonical lexical and temporal search execute independently.
5. Graph and semantic projection strategies execute independently when available.
6. `RetrievalPlanner` fuses only actual returned candidates and records every attempted, succeeded, and failed strategy.
7. Explainable ranking separates authority, trust, confidence, relevance, importance, and recency.
8. `ContextBudgetAllocator` returns a bounded hydration bundle.

No backend failure is represented as zero results.

## Curation and lifecycle

- Promotion is default-deny and evidence-bearing.
- Procedural synthesis emits review candidates and never auto-applies rules.
- Retention archives by policy and preserves referenced history.
- Supersession is non-destructive.
- Lineage replay detects cycles and missing parents.
- Phase locks are task-bound, conflict-free, expiring receipts that can be reverified.
- Verified deletion redacts canonical content immediately and completes only after required projection erasure succeeds.

## Projection erasure

Projection writes must return or establish a stable episode locator. The locator is stored in the canonical store as a `ProjectionLink`. A deletion outbox event loads that locator and invokes the provider deletion operation. Graphiti uses `delete_episode`; Zep uses `graph.episode.delete`. The link is removed only after provider confirmation, then the canonical deletion receipt becomes complete.

## Failure and recovery

- Authentication, authorization, admission law, canonical persistence, and audit receipts fail closed.
- Optional projection and extraction failures produce explicit partial or failed receipts.
- A canonical write becomes durable during the operation or raises; there is no deferred, queued-but-successful outcome (ADR-070).
- Outbox retries use bounded exponential backoff and terminal dead state.
- No direct database emergency path exists.

## Extension model

Add a store by implementing `RecordStore` and passing conformance tests. Add a projection by implementing `ProjectionAdapter`, returning stable locators, and passing search, health, and erasure tests. Add an ingestion source by constructing typed requests and calling `MemoryService`. Add enrichment through idempotent outbox consumers. Do not add another memory control plane.
