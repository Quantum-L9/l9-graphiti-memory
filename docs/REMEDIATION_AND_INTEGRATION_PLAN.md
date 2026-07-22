<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/REMEDIATION_AND_INTEGRATION_PLAN.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Remediation and Integration Register

## Decision

The accumulated findings required a compatibility-preserving v2 replatform. Version 2.1 closes the recursive harvest gap by implementing all in-scope concepts, rejecting out-of-scope ownership explicitly, and naming the remaining external validation blockers.

## Closed remediation register

| ID | Finding | Resolution | State |
|---|---|---|---|
| P0-1 | packaged registry path broken | packaged resource plus explicit override | implemented |
| P0-2 | hooks depended on Cursor-Governance paths | installed entrypoint adapters | implemented |
| P0-3 | MCP bypassed validation | all handlers call `MemoryService` | implemented |
| P0-4 | phase lock always granted | conflict-free, task-bound, expiring, verifiable receipt | implemented |
| P0-5 | server/client provider dialect mismatch | canonical local inventory plus Graphiti live-tool negotiation | implemented |
| P0-6 | caller-selected namespaces | server-derived principal and namespace policy | implemented |
| P0-7 | wheel could not resolve registry | package data and installed-wheel smoke | implemented |
| P0-8 | desktop config persisted secrets | command-only config writers plus secret scan | implemented |
| P0-9 | preflight checked wrong registry | installed-resource runtime check | implemented |
| P0-10 | direct script invocation failed | package entrypoints and `python -m` | implemented |
| P0-11 | no write-bypass enforcement | AST assurance gate | implemented |
| P0-12 | schema evolution unwired | mandatory read-time upcasting | implemented |
| P0-13 | direct DB reliability fallback | canonical ingress recovery plus atomic outbox | implemented |
| P0-14 | enrichment inside core commit | asynchronous projection and curation consumers | implemented |
| P0-15 | provider deletion could not be proven | persistent projection links and locator-aware erasure | implemented |
| P1-1 | disconnected tests | unified pytest and release validation | implemented |
| P1-2 | documentation maturity drift | regenerated architecture, runbook, ADR, manifest, validation, and harvest ledger | implemented |
| P1-3 | legacy extractor unwired | typed document, repository, atomic, and provider extraction | implemented |
| P1-4 | taxonomy drift | controlled `MemoryClass` contract | implemented |
| P1-5 | confidence without evidence | confidence, evidence, provenance, and source-range validation | implemented |
| P1-6 | no promotion lifecycle | default-deny promotion with receipts | implemented |
| P1-7 | monolithic episode blobs | atomic assertions with source records | implemented |
| P1-8 | identity/preference mixed with facts | distinct profiles and purpose-bound consent | implemented |
| P1-9 | destructive pruning | archive-first reference-aware retention | implemented |
| P1-10 | hybrid retrieval labels without independent execution | strategy-specific canonical and provider calls with receipts | implemented |
| P1-11 | provenance-incomplete insight generation | evidence-bound extractor and typed failure semantics | implemented |
| P1-12 | pass-only validation | executable evidence-bearing gates | implemented |
| P1-13 | semantic/episodic/procedural ownership unclear | versioned taxonomy and boundary ADR | implemented |
| P1-14 | bi-temporal claim unproved | valid-time and transaction-time coordinates and queries | implemented |
| P1-15 | mutable caller governance context | immutable server-derived principal | implemented |
| P1-16 | no tenant isolation contract | tenant-aware store port and conformance suite | implemented |
| P1-17 | normalization scattered | canonical normalization and content digests | implemented |
| P1-18 | retention ignored references | reference-aware archive decisions | implemented |
| P1-19 | lineage replay absent | references, cycle detection, and orphan reporting | implemented |
| P1-20 | sprawling public surface | SDK-first service with thin CLI, MCP, and hooks | implemented |
| P1-21 | schema/config/wiring drift | dedicated assurance scanners | implemented |
| P1-22 | no explainable importance policy | versioned ranking factors | implemented |
| P1-23 | no source distillation | offline evidence-preserving distiller | implemented |
| P1-24 | procedural learning could auto-apply | governed candidate worker and approval boundary | implemented |
| P1-25 | checkpoint utility implied checkpoint ownership | integrity utility only, ownership rejected | implemented |
| P1-26 | no explicit harvest convergence proof | 44-decision machine-validated coverage ledger | implemented |

## Explicit boundary rejections

The package does not own:

- the canonical `TransportPacket` model
- agent execution or checkpoints
- world-model updates
- raw private reasoning traces
- a duplicate L9-Ops-MCP memory control plane
- mandatory PostgreSQL, Redis, Neo4j, LangGraph, or LLM infrastructure
- private chat-history fixtures

These decisions are binding in the ADR ledger and coverage map.

## External validation blockers

The source implementation is complete, but production release remains gated on:

1. Live Graphiti add, search, delete, and replay proof
2. Live Zep add, search, delete, and replay proof
3. Production-like migration and rollback rehearsal
4. Credential loading and rotation rehearsal
5. Hosted Ruff, strict mypy, CodeQL, branch protection, and release-environment proof

These are `blocked_external`, not hidden as implementation gaps.

## Integration slices

1. Contract kernel and compatibility shell
2. Security, consent, and persistence controls
3. Retrieval, curation, lineage, and phase locks
4. Projection adapters, locator persistence, deletion, and recovery
5. Assurance, packaging, migration, and hosted release proof

The ZIP contains the converged source tree. A repository owner may still split review into these slices to control blast radius.
