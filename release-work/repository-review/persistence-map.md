<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: release-work/repository-review/persistence-map.md
layer: repository_review
owner: memory-control-plane
status: active
version: 2.2.0
pinned_sha: 16d5305c0124d85bf06b719c5bac4c516bfe9085
generated: 2026-07-26
generated_by: Manus AI repository review
/L9_META -->

# Persistence Map

This map records where every class of durable state lives at pinned SHA `16d5305c0124d85bf06b719c5bac4c516bfe9085`, who owns it, and how it is created, migrated, and erased. Authority: ADR-025 (storage source of truth), ADR-004/ADR-029 (temporal model), ADR-008 (idempotency and supersession), ADR-018/ADR-055 (outbox and recovery), ADR-035/ADR-047 (schema migration), ADR-057 (verified erasure).

## A. Canonical store (source of truth)

The `RecordStore` port (`src/l9_graphite_memory/ports/record_store.py`) is the single canonical owner of durable memory state. The default adapter is SQLite (`adapters/sqlite_store.py`) at `~/.local/share/l9-memory`; `adapters/in_memory_store.py` serves tests and ephemeral runs. Any future store must implement the same port and pass `tests/conformance/test_store_contract.py`.

| Persisted entity | Content | Write discipline |
|---|---|---|
| `MemoryRecord` | Typed record with tenant, namespace, memory class, content, digests, confidence, schema version, bi-temporal coordinates (valid-time and transaction-time) | Created only through `MemoryService`; never overwritten — corrections create new records plus supersession status events |
| `MemoryStatusEvent` | Lifecycle transitions (admitted, quarantined, promoted, archived, superseded, redacted) | Append-only |
| Operation receipts | Typed evidence receipts for write, search, hydration, deletion, projection outcomes | Written atomically with the operation they evidence (ADR-046) |
| Phase-lock receipts | Expiring snapshot-verification receipts (`gate_ttl_minutes: 30` default) | Verified by the local guard; expiry enforced (ADR-050) |
| Outbox events | Durable projection intents with attempt counts and next-attempt times | Enqueued in the same atomic transaction as the canonical write; retried with bounded backoff to a terminal dead state |
| Idempotency mappings | Tenant + namespace + idempotency key (or digest-derived key) to record ID | Exact replay returns the original record ID; retries never duplicate outbox effects |
| `ProjectionLink` | Stable provider locator per projected record (Graphiti episode ID, Zep episode ID) | Persisted when projection succeeds; removed only after provider-confirmed erasure |

## B. Atomicity and temporal guarantees

A canonical write persists the record, its lifecycle status, its receipt, and its projection outbox event in one atomic transaction; asynchronous enrichment can never leave the core commit half-applied (ADR-046). Every record carries explicit valid-time and transaction-time coordinates, so reads can filter by either axis and historical truth is never destroyed (ADR-004, ADR-029). Prior truth is never overwritten: supersession preserves the superseded record and its lineage (ADR-008), and lineage replay (`lineage/replay.py`) traverses explicit references with cycle detection (ADR-051).

## C. Projections (rebuildable, never canonical)

Graph and semantic projections in Graphiti (`projection_backend: http`) or Zep Cloud (`projection_backend: zep`) are deletable and rebuildable derivations; they cannot create canonical records, grant authority, or define lifecycle state (ADR-025). The `none` backend is fully functional. Projection state is reconciled through the outbox: batch size 50, base delay 5 seconds, maximum 8 attempts by default (`config/memory.yaml.example`).

## D. Secondary durable state

| State | Location | Owner |
|---|---|---|
| Ingress write recovery queue | `recovery/write_queue.py` under `~/.local/state/l9-memory` | Stores accepted writes only while the canonical service is unavailable; replays exclusively through `MemoryService` — no direct-database emergency path (ADR-055) |
| Guard/hook state | New state directory, with legacy read of the former `~/.cursor/graphiti-state` path | Local receipt guard (ADR-061); migration documented in `docs/COMPATIBILITY_MATRIX.md` |
| Generated client configs | `config_writer` outputs (e.g., `mcp.json`) | Contain no tokens (ADR-016); drift-gated by `check_config_drift.py` |
| Packaged resources | `resources/defaults.yaml`, `memory_contract.yaml`, `group_registry.yaml` | Read-only configuration authority (ADR-020, ADR-037) |
| Validation evidence | `validation/` tree with `SHA256SUMS` | Immutable release evidence; regenerated only by `generate_validation_evidence.py` |

## E. Schema evolution

Records persist their schema version. The schema registry (`schema/registry.py`) holds a deterministic upcasting graph (`schema/upcasters.py`); legacy v0.2 records are upcast on read without mutation of stored bytes until an explicit migration writes new versions (ADR-035, ADR-047, `MIGRATION.md`). Unknown or future versions produce typed failures rather than silent coercion.

## F. Erasure and privacy

Verified deletion (ADR-024, ADR-057) redacts canonical content immediately, leaving a redacted tombstone that preserves referential integrity, then completes the deletion receipt only after required projection erasure is confirmed: Graphiti via `delete_episode`, Zep via `graph.episode.delete`, keyed by the persisted `ProjectionLink` locator. Sensitive profile classes additionally require current purpose-bound consent at write time (ADR-049). SQLite at-rest encryption is a documented non-goal (`SECURITY.md`); confidentiality relies on filesystem permissions and the no-plaintext-secrets rule.
