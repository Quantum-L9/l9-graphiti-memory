# ADR-072: Shared Canonical Store Backend

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-072-shared-canonical-store-backend.md
layer: adr
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-08-20
/L9_META -->


**Date:** 2026-08-20
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.3+

## Status

Accepted

## Context

`build_store` constructed a `SQLiteRecordStore` unconditionally. Canonical
memory therefore lived in one file, and the set of agents that shared a memory
was exactly the set of processes that could open that path.

That is correct for a single developer on one machine and wrong for every other
deployment. Two agents on different hosts each had their own canonical store and
each believed it was authoritative. A scheduled maintenance run on a CI runner
would operate on an empty database created by its own checkout. Once ADR-070
removed local queueing as a way to paper over an unreachable store, the
durability and reachability of canonical state became a first-order requirement
rather than an implementation detail.

`RecordStore` was audited for SQLite-specific semantics before this decision.
It has none: every method is expressed in records, receipts, status events,
outbox events, projection links, and phase locks. A conforming shared adapter
was therefore possible without changing the port.

## Decision

`MemorySettings.store_backend` selects the canonical backend: `"sqlite"`
(default) or `"postgres"`. `PostgresRecordStore` implements `RecordStore` with
the same transaction boundaries as the SQLite adapter, so a canonical write
still commits the record, its lifecycle status event, its receipt, and its
projection outbox event atomically or not at all.

Selecting `"postgres"` requires an explicit `postgres_dsn`
(`L9_MEMORY_POSTGRES_DSN`). Configuration validation and `build_store` both
reject a shared backend without one, so a misconfigured deployment fails at
startup instead of silently writing to a process-local file.

The driver is imported lazily and ships in the `postgres` extra, so the base
package keeps its two runtime dependencies.

SQLite remains fully supported for local and test operation. It is not a
distributed authority and is not presented as one: `MemorySettings.is_shared_store`
reports which class of backend is in force.

The store conformance suite is parameterized over `memory`, `sqlite`, and
`postgres`. The PostgreSQL cases run whenever `L9_MEMORY_TEST_POSTGRES_DSN` is
set and skip loudly otherwise, so a missing database is visible as a narrowed
matrix rather than a silent pass.

## Alternatives Considered

- Keep SQLite everywhere and share the file over a network filesystem
- Add a synchronization or replication layer over SQLite files
- Adopt an ORM to abstract both backends
- Add a second `RecordStore` implementation on PostgreSQL

## Rejected Alternatives

- SQLite over NFS or SMB has documented locking failure modes and would make
  canonical durability depend on filesystem semantics the process cannot verify.
- File synchronization makes every replica an independent writer with
  last-writer-wins conflict resolution, which silently destroys canonical
  records; ADR-025 already forbids treating a derivation as authority.
- An ORM would hide exactly the transaction and locking semantics this store
  depends on, and would add a large dependency to a package that currently has
  two.

## Invariants

- `RecordStore` has no backend-specific semantics
- A canonical write is atomic across record, status, receipt, and outbox on
  every backend
- `store_backend: postgres` without a DSN fails at configuration and at
  construction
- No backend selection silently falls back to another backend
- SQLite is never described or configured as shared authority

## Consequences

Positive: Multi-agent and scheduled deployments have one canonical authority.
Maintenance can run anywhere with credentials rather than only where the file
lives. Concurrency primitives the outbox needs (`FOR UPDATE SKIP LOCKED`) are
available.

Negative: Shared deployments gain an operational dependency with its own
backup, migration, and availability requirements. The conformance matrix needs
a live database, so CI must provision one to exercise the shared backend.

## Security Impact

The DSN carries credentials and is resolved through the existing runtime secret
path; it is never committed. Reaching the store now crosses a network boundary,
so deployments must restrict access to the database and use TLS in the DSN.
Statement timeouts are bounded (`postgres_statement_timeout_ms`) so a hostile or
pathological query cannot hold a connection indefinitely.

## Migration Impact

Existing SQLite deployments are unaffected and require no action; the default is
unchanged. Moving to the shared backend is an explicit operator decision.
Migrating existing canonical data between backends is a separate, evidence-bound
operation and is not authorized by this decision.

## Validation Requirements

- The store conformance suite passes on all three backends
- Configuration tests prove a DSN-less shared backend is rejected
- Tests prove two SQLite files are independent authorities
- Tests prove two independent clients of the shared backend observe one
  canonical state without file synchronization

## Rollback Conditions

Set `store_backend` back to `sqlite`. Records written to the shared backend stay
there; they are not copied back, so rollback after shared writes requires an
explicit data migration.

## Supersedes / Superseded By

Extends ADR-025: the canonical store remains the single source of truth, and
this decision only widens where that store may live.

No later ADR supersedes this decision as of 2026-08-20.
