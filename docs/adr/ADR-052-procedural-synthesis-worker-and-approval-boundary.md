# ADR-052: Procedural Synthesis Worker and Approval Boundary

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-052-procedural-synthesis-worker-and-approval-boundary.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->


**Date:** 2026-07-22
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.1+

## Status

Accepted

## Context

Repeated successful episodes can suggest reusable procedures, but automatic promotion would let statistical repetition rewrite operating law.

## Decision

A deterministic PatternProceduralSynthesizer groups corroborated successful records and emits META-class procedural candidates. ProceduralSynthesisWorker submits candidates through MemoryService with source references and review-required metadata. Promotion to PROCEDURAL remains default-deny and requires governance approval or test-backed evidence.

## Alternatives Considered

- Auto-apply generated procedures
- Store unreferenced procedure summaries
- Place synthesis in the core write transaction

## Rejected Alternatives

- Auto-application expands authority
- Unreferenced procedures are unauditable
- Synthesis is optional enrichment and must not block core persistence

## Invariants

- Synthesis never auto-applies operational changes
- Every candidate references supporting records
- Minimum support is explicit
- Candidate writes use the canonical service

## Consequences

Positive: Repeated outcomes can become governed procedural memory

Negative: Candidate review and promotion add deliberate friction

## Security Impact

The approval boundary prevents self-modifying policy. Candidate content is still subject to normalization and admission.

## Migration Impact

Legacy heuristic artifacts import as META candidates requiring review, not active PROCEDURAL memory.

## Validation Requirements

- Minimum-support and dry-run tests
- MCP and CLI synthesis surface tests
- Promotion default-deny tests

## Rollback Conditions

Disable the synthesis worker; preserve source episodes and candidate receipts for review.

## Supersedes / Superseded By

Implements the deferred worker in ADR-045 and operationalizes ADR-009.

No later ADR supersedes this decision as of 2026-07-22.
