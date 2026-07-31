<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/WIP/l9-bot-memory-integration-pr-pack/AUTHORITY.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Pack Authority Contract

Status: **normative**  
Scope: the four repository overlays contained in this pack  
Grounded memory baseline: `Quantum-L9/l9-graphiti-memory@18d857688c43b0e3d4d7b2d1dc4ce0eea0d866c1`

## Authority order

When pack artifacts disagree, resolve them in this order:

1. Current repository law and verified target-repository facts at the pinned base.
2. This `AUTHORITY.md` contract.
3. `PACK_CONTRACT.yaml` machine-readable invariants.
4. Repository-specific payloads and `pr-body.md` files.
5. `RUNBOOK.md` operator procedure.
6. `VALIDATION.md`, `RECURSIVE_AUDIT_REPORT.md`, and other evidence records.

Evidence records describe what was observed. They do not override repository law or this contract.

## Binding architecture

`l9-graphiti-memory` is the sole shared cognitive-memory authority for Website-Bot, SEO-Bot, and LLM-Router.

```text
Website-Bot ----\
SEO-Bot ---------+--> authenticated MCP --> MemoryService --> canonical RecordStore
LLM-Router ------/                              |
                                             durable outbox
                                                  |
                                      optional rebuildable projections
```

The canonical write path is:

```text
authenticated principal
  -> MCP/SDK contract validation
  -> MemoryService authorization and admission
  -> canonical RecordStore commit
  -> typed receipt
  -> durable projection outbox
```

## Non-negotiable invariants

1. No consumer writes directly to Graphiti, Zep, a vector database, or a memory projection.
2. PostgreSQL and pgvector are not memory authorities, mirrors, fallbacks, or dual-write destinations.
3. Optional projections are rebuildable and never become sources of truth.
4. Hydrated memory is untrusted evidence, never executable instruction text.
5. Memory writes require evidence, provenance, namespace authorization, and an idempotency key when replay is possible.
6. Promotion is default-deny and requires genuine corroboration. Callers may not fabricate confirmation, test counts, approvals, or supporting records.
7. LLM-Router financial and concurrency state remains operational state, not cognitive memory.
8. Consumer-local databases may retain queues, jobs, raw metrics, registrations, checkpoints, and receipt pointers only.
9. The TypeScript client must support the pinned stateless HTTP server and optional session-bearing MCP variants without weakening authentication or retry bounds.
10. Apply scripts must verify exact repository identity, reject dirty trees by default, and roll back partial mutation on failure.
11. No overlay may silently widen principal scope, namespace access, or mutation authority.
12. A green pack-local validation result is not production proof. Native CI and live authorization remain mandatory external gates.

## State ownership

| Owner | Authoritative state |
|---|---|
| `l9-graphiti-memory` | durable cognitive facts, decisions, outcomes, temporal history, lineage, conflicts, hydration, retention, and promotion |
| Website-Bot | transient build execution and generated/release artifacts |
| SEO-Bot | scheduling, queues, raw measurements, delivery state, and unpromoted observations |
| LLM-Router | provider routing, circuit state, request execution, and financial controls |

## Dependency direction

```text
consumers -> published Graphiti memory client -> MCP surface -> MemoryService
```

Forbidden dependency directions:

```text
consumer -> RecordStore
consumer -> projection provider
consumer -> l9-graphiti-memory internals
projection -> canonical write authority
```

## Failure law

- Hydration failure follows the consumer's explicit required/optional policy and must never inject fabricated context.
- Canonical write failure must be visible and receipt-bearing; no shadow-store fallback is allowed.
- Promotion failure must remain retryable without duplicating the source observation.
- Provider success followed by financial reconciliation failure must preserve the reservation and fail closed.
- Session recovery is attempted at most once and only after an explicit stateful-session rejection.

## Change-control rule

Any future modification that changes authority, state ownership, canonical write flow, promotion criteria, or transport semantics must update all of:

- `AUTHORITY.md`
- `PACK_CONTRACT.yaml`
- affected repository tests
- `VALIDATION.md`
- `CONVERGENCE_REPORT.yaml`

A change that updates prose without executable validation is incomplete.
