<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: deployment/generated-data/migration-runbook.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Generated-Data Integration Migration Runbook

## Purpose

Apply and verify store changes required for governed candidate ingestion,
reuse-event persistence, source invalidation, and structured selector indexes.

The canonical store remains authoritative. External Graphiti projection is
optional and must not block canonical migration.

## Preconditions

1. Run from the `l9-graphiti-memory` checkout.
2. Confirm the generated-data integration source wave is merged.
3. Confirm no second canonical write path exists.
4. Identify the canonical database path.
5. Stop writers or place the service in its documented maintenance mode.
6. Verify sufficient disk space for at least two full database copies.

## Backup

```bash
mkdir -p validation/generated-data-migration
python deployment/generated-data/verify_backup_restore.py \
  --database /path/to/canonical.sqlite3 \
  --output-dir validation/generated-data-migration/backup-check
````

Do not proceed unless the source, backup, and restored integrity checks return
`ok`.

## Inspect

```bash
python deployment/generated-data/verify_migration.py \
  inspect \
  --database /path/to/canonical.sqlite3
```

Record the table inventory, index inventory, migration version, repository SHA,
and backup hash.

## Dry run

```bash
python deployment/generated-data/verify_migration.py \
  dry-run \
  --database /path/to/canonical.sqlite3
```

Dry-run operations must use a temporary copy. They must never modify the source.

## Apply

Use the repository's existing migration command discovered by the integration
preflight. Never invent an unregistered SQL path.

```bash
python deployment/generated-data/verify_migration.py \
  apply \
  --database /path/to/canonical.sqlite3 \
  --backup /path/to/verified-backup.sqlite3
```

## Verification

Verify:

* SQLite integrity is `ok`.
* Existing active, quarantined, superseded, archived, and deleted records remain readable.
* Existing search and hydration lifecycle behavior is unchanged.
* Reuse events survive service restart.
* Invalidation events survive service restart.
* Structured selector tables and indexes exist.
* Selector lookup plans do not require an ordinary full-record scan.
* Projection outage does not affect canonical reads or writes.

```bash
python deployment/generated-data/verify_selector_indexes.py \
  --database /path/to/canonical.sqlite3
```

## Rollback

1. Disable generated-data ingress, reuse, and invalidation public operations.
2. Stop writers.
3. Preserve the failed migrated store for evidence.
4. Restore the verified backup.
5. Start the canonical service with projection disabled.
6. Run existing health, search, and hydration checks.
7. Replay only operations with durable receipts and stable idempotency keys.
8. Do not rerun the original subagents.

## Evidence

Retain:

* source database hash;
* backup hash;
* migrated database hash;
* migration command output;
* integrity checks;
* selector index verification;
* repository SHA;
* Cursor-Governance SHA;
* rollback decision, when used.
