# ADR-089: Graph Intelligence Public Surfaces and Observability

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-089-graph-intelligence-public-surfaces-and-observability.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-09-26
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+ (campaign `l9-memory-graph-intelligence-v1`, slice PR-F)

## Status

Accepted

## Context

ADR-084..ADR-088 built the graph-intelligence plane behind
`GraphIntelligenceService`. Consumers need stable provider-neutral entry
points, a capability and health report that keeps each dimension separate, and
operational metrics — without adding Gate routing semantics to this dependency
package (the future `l9-memory` node owns that boundary) and without changing
what `memory.search` or `memory.health` mean (GI-036).

## Decision

1. **SDK.** `MemorySDK.graph(request) -> GraphIntelligenceReceipt` and
   `MemorySDK.graph_capabilities() -> GraphCapabilityReport` run under the
   SDK's bound principal. Without an injected service the SDK composes one
   over `NullGraphIntelligence`: structural operations report
   `capability_unavailable`; graph/semantic search still use the projection.
2. **MCP.** One typed tool per operation, memory-owned names
   `memory.graph.search` … `memory.graph.structural_embedding`, plus
   `memory.graph.capabilities`. Each input schema mirrors
   `graph-intelligence-request.schema.json` with `additionalProperties: false`
   and no tenant, group, or query-text field; the operation comes from the tool
   name. The tool application composes the graph service lazily, so
   constructing it touches no service state.
3. **Capability receipt.** `MCP_OPERATION_TOOLS` reports `graph.*`
   operations for the MCP transport. Like the agent write doors they are MCP +
   SDK surfaces, not CLI lifecycle operations, so CLI/MCP parity (ADR-082) is
   unchanged.
4. **Capability and health report** (`GraphCapabilityReport`): scope scheme
   and version, served capabilities (backend ∪ projection search strategies),
   backend health (reachability, versions, schema fingerprint and
   compatibility, analytics availability, scope conformance), projection
   strategies, maturity ceiling, link-prediction flag, `required`, `ready`, and
   observed GDS catalog cleanup failures. `memory.health` is unchanged;
   `/readyz` adds a `graph` section and fails readiness on an unhealthy graph
   backend **only** when `graph_intelligence_required` is set.
5. **Metrics** (`observability.graph_metrics`, process-local, exporter-neutral):
   `memory_graph_query_total{operation,status}`,
   `memory_graph_query_latency_ms{operation}`,
   `memory_graph_result_nodes{operation}`,
   `memory_graph_result_edges{operation}`,
   `memory_graph_scope_denied_total`,
   `memory_graph_rehydration_drop_total{reason}`,
   `memory_graph_gds_cleanup_failure_total`,
   `memory_graph_provider_failure_total{provider,operation}`,
   `memory_graph_partial_receipt_total{operation}`.
   One structured log line per operation carries operation, status, scope
   digest, algorithm, counts, latency, result digest, and failure classes —
   never memory content, credentials, raw vectors, tenant ids, or query text.

## Alternatives Considered

- A single `memory.graph` tool with an operation argument.
- Adding graph state to `HealthReport`.
- Gate-shaped action names and routing in this package.
- A Prometheus client dependency.

## Rejected Alternatives

- One tool per operation gives each a typed, discoverable contract and maps
  one-to-one onto future Gate actions.
- Changing `HealthReport` or `memory.health` would alter an existing contract.
- Gate routing belongs to the constellation node, not the dependency package.
- An exporter is a deployment choice; the registry is exporter-neutral.

## Invariants

GI-005, GI-006, GI-007, GI-010, GI-029, GI-031, GI-033, GI-036.

## Consequences

- In-process consumers and MCP clients can use every capability through the
  memory boundary with typed receipts.
- Operators can see served capabilities and why others are unavailable.

## Security Impact

No surface accepts scope authority or query text; smuggled `tenant_id` or
`cypher` arguments fail validation. Logs and metrics carry no content.

## Migration Impact

Additive tools and SDK methods. `/readyz` gains a `graph` section.

## Validation Requirements

`tests/unit/test_graph_public_surfaces.py`: tool inventory; schemas without
scope or query fields; MCP receipt; smuggled scope/Cypher rejected; capability
report dimensions; capability receipt with CLI parity intact; SDK default and
injected service; metrics and content-free logs; readiness gating. Existing
MCP, SDK, parity, and search suites stay green.

## Rollback Conditions

Revert the slice; the service remains reachable in-process through the
runtime composition.

## Supersedes / Superseded By

Extends ADR-014, ADR-082, ADR-085..ADR-088. Superseded by none.
