# ADR-086: Structured Source Invalidation Lifecycle

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-086-structured-source-invalidation-lifecycle.md
layer: adr
owner: memory-control-plane
status: active
version: 2.5.0
updated: 2026-10-02
/L9_META -->


**Date:** 2026-10-02
**Decision owner:** Quantum-L9 memory architecture
**Applies to:** `Quantum-L9/l9-graphiti-memory` v2.5+

## Status

Accepted

## Context

Governed generated-data candidates carry structured `invalidation_conditions`
(`{condition_type, selector}`), and Cursor-Governance's repository event bridge
sends a structured `SourceInvalidationRequest` when a source changes. The
`invalidate-source` command and `memory.invalidate_source` tool accepted that
request, but `GeneratedDataService.invalidate_by_source` only wrote a META
record through `MemoryService.write`, always returned `matched=0`, and fell back
to the namespace `default` when no repository was given. The request model used
`extra="allow"`, so the deployed producer's `selectors[]` was silently ignored
and only a singular `selector` dictionary was modeled. No record was ever
archived, nothing left retrieval, and an `applied` receipt proved nothing.

The canonical lifecycle machinery already exists: governed transitions
(ADR-074), target-aware retirement intents on the outbox (ADR-084), and the
retrieval rule that only ACTIVE records are ordinary results.

## Decision

1. **Locked path.** `GeneratedDataService` validates the request contract and
   calls `MemoryService.invalidate_by_source`. The service resolves, authorizes
   and plans; `RecordStore.commit_source_invalidation` commits. The adapter
   calls no store, projection, Graphiti, or Zep method.
2. **Lifecycle state.** Source invalidation moves matching ACTIVE records to
   ARCHIVED through the governed lifecycle table (ACTIVE -> ARCHIVED requires
   READ and MAINTAIN on the record's namespace). No new `MemoryState` is added
   and quarantine is not used: the record was admitted correctly and has only
   stopped being current. Ordinary search and hydration exclude it; a search
   with `include_archived` (generated-data `include_invalidated`) returns it.
   Content, evidence, provenance, metadata and lineage are untouched; nothing is
   deleted and no replacement is created.
3. **Request contract (`memory-control-plane/v1`, unchanged).** Canonical form:
   `event_id`, `event_type`, `repository`, `from_sha`, `to_sha`,
   `selectors[]`, `delete_memory=false`. A selector is `selector_id`,
   `selector_type`, `selector_value`; the deployed bridge spellings
   `condition_type`/`selector` and its typed `change_kind`/`previous_path` are
   modeled explicitly, as are its envelope fields `schema_version` (major 1),
   `kind`, `create_replacement_record=false` and `metadata`. Every other field
   fails closed (`extra="forbid"`). The legacy singular `selector` is an
   explicit compatibility form, normalized to a one-element `selectors[]`;
   `selector` and `selectors` together, or neither, are rejected. Canonical
   requests require `event_id` and `repository`; a legacy request without
   `event_id` receives `legacy-invalidation-<digest>` derived from the
   normalized request body. Matching is equality on
   `(repository, selector_type, selector_value)`; a legacy request without
   `repository` matches across repositories. There is no natural-language
   matching.
4. **Authorization before mutation.** All matching record IDs are resolved
   first, then every affected namespace, then the principal is authorized for
   every namespace. One denial rejects the whole operation with nothing
   mutated. A rejection is not persisted, so the same operation can apply once
   the grant exists.
5. **Atomicity.** One operation commits, in one store transaction: the
   operation record, one `LifecycleTransitionReceipt` per affected namespace,
   the status events, one retirement outbox intent per copy holder (the
   existing ADR-084 `memory.record.retire` path), one revalidation requirement
   per archived record, and the deactivation of the archived records'
   selectors. A stale previous state on any record rolls the whole operation
   back and the receipt is `rejected`.
6. **Receipt.** `status` stays `applied`/`rejected`; there is no partial
   success. The receipt gains `event_id`, `transitioned`, `record_ids`,
   `lifecycle_receipt_ids`, `revalidation_requirement_ids`, and `deleted`,
   which is always false. An identical replay returns the established result
   without mutating again; the same identity with a different body is
   `rejected` as a conflict. A zero-match operation is `applied` with
   `matched=0`, and is never live proof: the generated-data live proof requires
   `status == applied`, `matched > 0`, `transitioned > 0`, proven ordinary
   retrieval exclusion, proven historical visibility, and `deleted != true`.
7. **Selector persistence.** `commit_write` derives selector rows from the
   admitted record in the same transaction, through one pure mapping
   (`source_selectors_for_record`) that reads only a governed candidate's
   structured `repository` and `invalidation_conditions`. The mapping is
   all-or-nothing: unless every condition is exactly `{condition_type,
   selector}` strings, the record has no selectors. Statement text, provider
   content and search text are never read. A privacy deletion removes the
   record's selectors with the tombstone.
8. **Store schema 9.** SQLite and PostgreSQL add `memory_source_selectors`
   (`selector_id`, `record_id`, `repository`, `selector_type`,
   `selector_value`, `active`, `created_at`, `deactivated_at`; indexes
   `(repository, selector_type, selector_value, active)`, `(record_id, active)`,
   `(selector_type, selector_value, active)`), `source_invalidation_events`
   keyed by `(tenant_id, event_id)`, and `revalidation_requirements`. The 8 -> 9
   migration backfills selectors with the same mapping, so a backfilled
   selector equals the one admission would have written. `MEMORY_SCHEMA_VERSION`
   stays `2.2.0`: the serialized `MemoryRecord` is unchanged.

## Alternatives Considered

- A new `INVALIDATED` memory state.
- Quarantining invalidated records.
- One `transition_lifecycle` call per namespace.
- Matching selectors by scanning record metadata at request time.
- Keeping `extra="allow"` for backward compatibility.
- Bumping the control-plane contract version.

## Rejected Alternatives

- **INVALIDATED state.** Every retrieval, retention, projection and lifecycle
  rule would need a new branch for a state whose semantics are ARCHIVED's.
- **Quarantine.** Quarantine is review of an unadmitted candidate; using it
  for a record that is merely no longer current would put admitted memory back
  into review and change who may release it.
- **Per-namespace calls.** A failure in the second namespace would leave the
  first already archived: a partial success the contract forbids.
- **Request-time metadata scans.** A full-record scan per selector, and a
  matcher that could drift from what admission recorded.
- **`extra="allow"`.** It is how `selectors[]` was ignored; consequential
  requests fail closed on unknown fields.
- **Contract version bump.** The change is a bug fix: every previously valid
  structured request remains valid through modeled compatibility fields.

## Invariants

- MemoryService is the only path that mutates canonical lifecycle state; the
  generated-data adapter owns no mutation.
- A source invalidation never deletes, never replaces, and never transitions a
  record outside the governed lifecycle table.
- All transitions of one operation commit together or not at all.
- Selectors come only from structured metadata, losslessly, or not at all.
- Projection copies are retired through the existing outbox, per target.
- Caller identity remains server-derived; no grant is read from the request.

## Consequences

- Generated-data memory leaves ordinary retrieval when its source changes and
  carries an open revalidation requirement.
- Old structured clients keep working; clients that relied on unknown fields
  being ignored now receive a validation error.
- Matching is exact: a changed file path does not match a directory selector,
  and a rename matches on its new path only (`previous_path` is recorded, not
  matched).
- The invalidation receipt no longer carries a `write_receipt_id`; no write
  occurs.

## Security Impact

Invalidation now requires READ and MAINTAIN on every affected namespace, where
the former path required only WRITE on one namespace (or wrote to `default`).
A replay discloses the established result only to a principal holding the same
authority. Deletion removes derived selector rows, so no metadata copy survives
a verified deletion.

## Migration Impact

Store schema 8 -> 9 for SQLite and PostgreSQL, applied in place inside the
initialization transaction, idempotent, and restart safe: the backfill runs
only until schema 9 is recorded, selector IDs are deterministic, and inserts
ignore existing rows. PostgreSQL serializes concurrent initializers with a
transaction-scoped advisory lock. Historical records receive selectors only
when their structured metadata maps losslessly; archived or superseded records
receive inactive selectors. `MEMORY_SCHEMA_VERSION` and
`CONTROL_PLANE_CONTRACT_VERSION` are unchanged.

## Validation Requirements

- `tests/unit/test_source_invalidation_contract.py`: request forms, fail-closed
  fields, legacy identity derivation, lossless mapping, CLI protocol.
- `tests/integration/test_source_invalidation.py`, against the in-memory,
  SQLite and PostgreSQL stores: selector persistence, archival, retrieval
  exclusion and history, evidence and lineage, revalidation durability, outbox
  retirement, idempotency, conflicts, authorization and atomicity.
- `tests/integration/test_source_selector_migration.py`: fresh schema 9,
  8 -> 9 backfill and restart on SQLite and PostgreSQL, interrupted migration.
- `tests/deployment/generated_data/test_live_proof_fail_closed.py`: `applied`
  alone is not live proof.
- `bash scripts/validate_release.sh`.

## Rollback Conditions

Roll back if an invalidation archives a record no structured selector named,
commits part of an operation, deletes or replaces memory, or leaves an
archived record in ordinary retrieval. Disable invalidation dispatch first
(`L9_SGD_GRAPHITI_INVALIDATE_COMMAND`); records already archived stay archived
and can be restored to ACTIVE under ADMIN through `transition_lifecycle`.
Pre-ADR-086 code ignores the schema-9 tables and keeps working on a schema-9
store, but it neither writes selectors for new records nor removes them on a
privacy deletion, and the backfill does not rerun once schema 9 is recorded.
Restoring the pre-upgrade backup is therefore the clean rollback.

## Supersedes / Superseded By

Extends ADR-074 (projection retirement lifecycle), ADR-084 (target-aware
lifecycle), ADR-082 (consumer control-plane transport parity), and ADR-008
(idempotency). Supersedes none. Superseded by none.
