# ADR-086: Graph Intelligence Contracts, Receipts, and Evidence Binding

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-086-graph-intelligence-contracts-and-evidence-binding.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-09-25
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ (campaign `l9-memory-graph-intelligence-v1`, slice PR-C)

## Status

Accepted

## Context

ADR-085 introduced a read-only `GraphIntelligencePort` beside the projection
adapter. Structural results computed over a Graphiti projection are
projection-derived: an entity or relationship aggregates what Graphiti
extracted, not what memory admitted. Without a governing service, a caller
could mistake a provider node for a canonical record, widen scope through a
request field, receive "no relationships" when the provider was down, or run
an experimental algorithm as if it were authoritative.

## Decision

1. **Contracts** (`graph.contracts`), shipped with JSON Schemas in
   `resources/graph/` (`l9.memory.graph-intelligence-request.v1`,
   `l9.memory.graph-intelligence-receipt.v1`):
   - `GraphIntelligenceRequest`: operation, namespaces, one-of anchors
     (canonical record id, opaque entity UUID, or bounded text), relationship
     types matching `^[A-Z][A-Z0-9_]{0,63}$`, direction, `as_of`,
     `recorded_before`, algorithm, `required`, profile reference, and
     `GraphLimits` (depth ≤ 6, nodes ≤ 1000, edges ≤ 5000, paths ≤ 100,
     runtime ≤ 30 s). It has no tenant, group id, or query-text field.
   - `GraphProviderRequest`/`GraphProviderResult`: what a port receives
     (derived GraphScopeKey v1 groups only) and returns (nodes, edges, paths,
     scores with provider group ids and supporting episode UUIDs).
   - `GraphIntelligenceReceipt`: `COMPLETE | PARTIAL | FAILED`, scope digest,
     `authority_class = advisory_projection`, provider identity and versions,
     algorithm id/maturity/config digest, applied limits, results, supporting
     canonical record ids, unsupported projection observations, failures, and a
     deterministic result digest.
2. **Algorithm policy** (`graph.algorithm_policy`): a closed algorithm set per
   operation with declared maturity. Production/native defaults run when the
   capability is served; beta/alpha need the deployment maturity ceiling;
   link prediction (alpha) also needs its feature flag. Out-of-operation or
   unknown algorithms are refused; there is no semantic fallback for
   structural similarity.
3. **Evidence binding** (`graph.evidence`): each observation's supporting
   episode UUIDs are rehydrated from `RecordStore` and admitted only when tenant,
   authorized namespace, `ACTIVE` state, valid time at `as_of`, and transaction
   time before `recorded_before` all hold. Items without admitted support
   become `unsupported_projection_observations` (excluded from results). Items
   in an unauthorized provider group are discarded. Edges outside their
   validity at `as_of` are excluded. Paths and scores need every member node
   supported. Structural embeddings return a digest and dimension; raw vectors
   only when the deployment allows them.
4. **Service** (`graph.service.GraphIntelligenceService`, composed by
   `runtime.build_graph_service` over the same store and `NamespacePolicy` as
   `MemoryService`):
   - authorizes every namespace for READ; the tenant is the principal's;
   - rejects out-of-policy relationship types, unserved capabilities,
     inadmissible algorithms, and anchors that are not the principal's active
     records before calling the provider (absent and foreign anchors get the
     same answer);
   - clamps runtime to the deployment ceiling and applies node/edge/path caps
     deterministically after evidence binding;
   - maps provider exceptions to `FAILED` with a normalized error class; raw
     provider text never reaches the caller;
   - returns `PARTIAL` for truncation, out-of-scope drops, or rehydration
     errors, and `FAILED` (with no results) when the request or deployment
     marks graph intelligence as required.

## Alternatives Considered

- Return provider nodes as memory search hits.
- Let callers pass the tenant or a group id for multi-tenant admin use.
- Treat an empty provider result after an error as `COMPLETE`.
- Let the adapter choose an algorithm substitute when one is unavailable.

## Rejected Alternatives

- Provider nodes are not canonical records; mixing them into `memory.search`
  would change its meaning (GI-036) and promote projection output (GI-004).
- Any caller-supplied scope defeats GI-010/GI-011.
- An empty `COMPLETE` after failure is exactly "provider outage reported as no
  relationships found".
- Silent substitution breaks receipt truthfulness (GI-032).

## Invariants

GI-004, GI-006, GI-010..GI-015, GI-023, GI-025..GI-030, GI-033/GI-034.

## Consequences

- Structural operations have a stable, provider-neutral answer shape before
  any provider implements them (PR-D/PR-E).
- Every graph answer is auditable: the digest binds scope, algorithm, results,
  and support.

## Security Impact

Scope is derived, never supplied. Cross-tenant support ids, foreign-group
items, and foreign anchors are dropped or refused without revealing whether
the foreign record exists. Provider error text is not exposed.

## Migration Impact

Additive. No persisted state; receipts are returned, not stored.

## Validation Requirements

- `tests/unit/test_graph_contracts.py`: payloads validate against the shipped
  schemas; no scope-authority or query-text fields; unbounded limits,
  Cypher-bearing relationship types, and malformed anchors are rejected.
- `tests/unit/test_graph_algorithm_policy.py`: defaults, admissibility,
  maturity and feature gates, identity digests.
- `tests/unit/test_graph_evidence_linking.py`: tenant, namespace, lifecycle,
  temporal, group, path, score, embedding, and store-failure cases.
- `tests/unit/test_graph_service.py`: complete receipt, derived groups only,
  determinism, authorization before provider, failure ≠ empty, capability and
  policy short-circuits, foreign anchors, truncation, runtime clamp, health
  cache; receipts validate against the schema.
- `tests/conformance/test_graph_intelligence_port.py`: every backend
  implements the port, exposes nothing forbidden, and refuses unserved
  operations.

## Rollback Conditions

Revert; no persisted state is created. `graph_intelligence_backend: none`
disables every operation.

## Supersedes / Superseded By

Extends ADR-085. Superseded by none.
