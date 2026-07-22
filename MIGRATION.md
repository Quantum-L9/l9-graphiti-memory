<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: MIGRATION.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Migration from v0.2

## Strategy

Version 2.1 is a compatibility-preserving replatform, not an in-place implementation patch. It retains valid entrypoints while replacing the internal control plane.

## Before cutover

1. Pin the v0.2 commit, package version, registry, and provider configuration.
2. Export legacy episodes and any provider episode identifiers available.
3. Back up local databases, Graphiti/Zep state, and gate state.
4. Keep v0.2 read-only during migration.
5. Create a rollback copy that is independently restorable.

## Data migration

Legacy episode-shaped JSON is accepted through the schema registry and import command:

```bash
l9-memory import legacy-episodes.jsonl --group-id target-namespace --dry-run
l9-memory import legacy-episodes.jsonl --group-id target-namespace
```

The upcaster maps `episode_body`, `reference_time`, `group_id`, and `kind` into current contracts, retains source metadata, and creates deterministic idempotency keys.

For document or repository sources:

```bash
l9-memory distill source.md --group-id target-namespace --dry-run
l9-memory bootstrap --root /path/to/repo --group-id target-namespace --dry-run
```

## Projection migration

Canonical v2.2 writes store provider locators in `projection_links`. Legacy provider data may not have stable locators. Inventory legacy episodes before enabling verified deletion. Reproject canonical records through the outbox so every new provider copy receives a tracked locator.

## Configuration migration

- Replace `GRAPHITI_TRANSPORT` with `L9_MEMORY_PROJECTION_BACKEND`.
- Keep `GRAPHITI_MCP_URL` and `GRAPHITI_MCP_TOKEN` only for the HTTP projection adapter.
- Use `L9_MEMORY_CONFIG` for YAML settings.
- Use `L9_MEMORY_REGISTRY_PATH` for an external registry override.
- Use explicit local or token-derived namespace claims.
- Do not copy credentials into Cursor or Claude JSON.

## Behavioral differences

- Graphiti and Zep are projections rather than canonical storage.
- Remote callers cannot choose arbitrary namespaces.
- Sensitive profiles require consent.
- Quarantine is durable and excluded from normal retrieval.
- Conflict checks deny phase locks when conflicts exist or retrieval is indeterminate.
- Search failure is not an empty result.
- Provider deletion must be confirmed before a deletion receipt completes.
- No implicit localhost, provider, or direct-database fallback exists.
- Direct source-script execution is replaced by package entrypoints or `python -m`.

## Cutover gates

- deterministic tests and assurance tools pass
- legacy import counts and hashes reconcile
- wheel install smoke passes
- namespace isolation and temporal queries pass
- projection locators are established for newly projected records
- rollback database copy is restored successfully
- optional live provider add/search/delete/replay soak completes

## Rollback

Stop v2.2 writers and workers, preserve the v2.2 database for diagnosis, restore the pinned v0.2 environment and separate data source, and verify read-only operation before reopening writes. Never point both versions at the same writable backend.
