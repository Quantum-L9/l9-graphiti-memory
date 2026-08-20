# ADR-055: Canonical Ingress Write Recovery Queue

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-055-canonical-ingress-write-recovery-queue.md
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

Superseded by ADR-070

## Context

A client-side or hook write can fail before the canonical outbox exists. Retrying with direct database writes would improve apparent availability by bypassing governance.

## Decision

Provide a filesystem-backed FileWriteRecoveryQueue for failed ingress requests. It stores the typed canonical request plus digest, replays only through MemoryService, preserves failed items, and emits a replay report. The canonical store outbox remains responsible for post-commit projection delivery.

## Alternatives Considered

- Direct database fallback
- Drop failed writes
- Reuse the post-commit outbox for pre-commit requests

## Rejected Alternatives

- Direct writes erase governance
- Dropping writes loses user intent
- Pre-commit requests and committed effects have different semantics

## Invariants

- Recovery entries contain canonical requests, not SQL
- Replay uses normal authorization and admission
- Successful replay removes the queue entry
- Failed replay is retained with error evidence

## Consequences

Positive: Ingress failure becomes resumable without weakening controls

Negative: Local queues require filesystem protection and operator replay

## Security Impact

Queue files may contain memory content and must inherit state-directory permissions. Secrets are not embedded.

## Migration Impact

Legacy fallback JSON files may be transformed into recovery entries after validation; ambiguous files remain quarantined.

## Validation Requirements

- Queue durability and replay tests
- Failed-entry retention tests
- CLI recovery command tests

## Rollback Conditions

Stop replay, preserve queue files, and process them with the previous validated service version.

## Supersedes / Superseded By

Completes ADR-018.

Superseded by ADR-070 on 2026-08-20: deferred canonical ingestion is no longer an
admitted write outcome. The queue described here is retired; legacy state is
drained one way by `l9_graphite_memory.migration.LegacyWriteQueueDrain`.
