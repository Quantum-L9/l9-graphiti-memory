<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/repository-review/provider-capability-matrix.md
layer: repository_review
owner: memory-control-plane
status: active
version: 2.2.0
pinned_sha: 16d5305c0124d85bf06b719c5bac4c516bfe9085
generated: 2026-07-26
generated_by: Manus AI repository review
/L9_META -->

# Provider Capability Matrix

This matrix records what each projection backend supports at pinned SHA `16d5305c0124d85bf06b719c5bac4c516bfe9085`. Sources: `src/l9_graphite_memory/transport.py`, `zep_transport.py`, `adapters/graphiti_projection.py`, `adapters/null_projection.py`, `adapters/factory.py`, `docs/COMPATIBILITY_MATRIX.md`, ADR-013, ADR-025, ADR-054, ADR-057.

Under ADR-025, every provider is a **rebuildable projection**, never a canonical store. Selection is by `projection_backend` in `memory.yaml` (`none` | `http` | `zep`), resolved by the adapter factory. With `projection_required: false` (default), projection failure degrades to explicit partial receipts; the canonical write is already durable.

## A. Capability table

| Capability | `none` (null projection) | `http` (Graphiti MCP) | `zep` (Zep Cloud) |
|---|---|---|---|
| Canonical durability | N/A — canonical durability always lives in RecordStore | Same | Same |
| Episode/graph write | No-op success | Yes — `add_memory` preferred, `add_episode` legacy dialect | Yes — via `zep-cloud` SDK graph API |
| Semantic/fact search | Not available; lexical and temporal strategies still serve reads | Yes — `search_memory_facts` preferred, `search_facts` legacy dialect | Yes — Zep graph search |
| Dialect negotiation | N/A | Yes — transport negotiates preferred vs. legacy tool names per server | N/A — SDK-versioned (`zep-cloud>=3,<4`) |
| Stable locator persisted | N/A | Yes — episode locator stored as `ProjectionLink` | Yes — episode locator stored as `ProjectionLink` |
| Verified erasure | Trivially complete | Yes — `delete_episode` by locator; deletion receipt completes only after confirmation | Yes — `graph.episode.delete` by locator |
| Health probe | Always healthy | Yes — surfaced through `l9-memory health` | Yes — surfaced through `l9-memory health` |
| Auth handling | None needed | Token via secrets boundary; never persisted in generated configs (ADR-016) | API key via secrets boundary |
| Failure semantics | Cannot fail | Typed per-strategy receipts (ADR-054); outbox retry, base 5 s, max 8 attempts, terminal dead state | Same outbox posture |
| Extra dependency | None | None beyond core (stdlib HTTP transport) | `zep` extra (`zep-cloud>=3,<4`) |
| Live validation status | Fully covered by local tests | **Blocked externally — RP-004** (live lifecycle proof) | **Blocked externally — RP-005** (live lifecycle proof) |

## B. Contract every provider must satisfy

A projection adapter implements the `ProjectionAdapter` port with four obligations: accept a projection intent and return a **stable locator**; support **search** appropriate to its modality; expose a **health** signal; and perform **locator-verified erasure**. Conformance is exercised by unit tests over each adapter and by the outbox integration tests (`tests/integration/test_outbox.py`); no backend failure may be represented as zero results — retrieval receipts record attempted, succeeded, and failed strategies per query (ADR-039, ADR-054).

## C. Degradation ladder

1. **Backend `none`** — the documented baseline: all canonical guarantees hold, retrieval runs lexical and temporal strategies, and graph/semantic strategies are recorded as not attempted.
2. **Backend configured, provider down** — canonical writes succeed; outbox events accumulate and retry with bounded exponential backoff; searches return typed partial receipts naming the failed strategy.
3. **Provider permanently dead** — outbox events reach the terminal dead state and are visible to operators (`RUNBOOK.md`); projections can be rebuilt wholesale from the canonical store after recovery because they are derivations (ADR-025).
4. **`projection_required: true`** — an operator may opt in to fail-closed projection, making projection success part of the write receipt.

## D. Explicit non-capabilities

No provider can create canonical records, grant or widen namespace authority, define lifecycle state, or serve as the deletion system of record. The constellation Gate is not a memory provider: `GateMemoryBridge` only packages memory receipts into injected TransportPackets for Gate-resolved dispatch (ADR-026, ADR-060). The LLM extraction provider (ADR-041) is an enrichment dependency with typed failure semantics, not a projection backend, and is therefore out of scope for this matrix.
