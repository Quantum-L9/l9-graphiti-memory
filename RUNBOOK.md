<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: RUNBOOK.md
layer: repository
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Runbook

## Install and verify

```bash
python -m pip install .
l9-memory resolve
l9-memory health
```

The default database is `~/.local/share/l9-memory/memory.sqlite3`. Gate and recovery state is under `~/.local/state/l9-memory`.

## Local standalone mode

No external credentials are needed:

```bash
export L9_MEMORY_PROJECTION_BACKEND=none
l9-memory write 'A durable observation' --kind observation --group-id l9-graphiti-memory --source operator
l9-memory search 'durable' --group-id l9-graphiti-memory
```

## Sensitive identity or preference memory

Identity and preference classes require purpose-bound consent. Supply the subject, purpose, evidence, and grant timestamp through the CLI flags or typed SDK contract. Do not convert implied behavior into consent.

```bash
l9-memory write 'user-1 prefers concise answers' \
  --kind preference \
  --group-id repo-a \
  --source explicit-user-message \
  --consent-subject user-1 \
  --consent-purpose 'remember communication preferences' \
  --consent-evidence 'message-123'
```

## Search, hydration, and phase locks

```bash
l9-memory search 'deployment decision' --group-id repo-a
l9-memory hydrate 'prepare deployment' --group-id repo-a
l9-memory conflicts --group-id repo-a
l9-memory phase-lock 'deploy release' --group-id repo-a
l9-memory verify-phase-lock 'deploy release' --group-id repo-a
```

A partial receipt means the canonical store succeeded while an optional strategy failed. A failed receipt means the canonical operation failed. Never treat either as an empty successful result.

## Lineage and curation

```bash
l9-memory lineage <record-id> --group-id repo-a
l9-memory promote <record-id> --group-id repo-a --reason 'corroborated by approved evidence'
l9-memory synthesize-procedures --group-id repo-a --dry-run
l9-memory prune --group-id repo-a --dry-run
```

Procedural synthesis creates candidates only. Promotion requires authority and policy evidence.

## Offline source ingestion

```bash
l9-memory distill path/to/document.md --group-id repo-a --dry-run
l9-memory import legacy.jsonl --group-id repo-a --dry-run
l9-memory bootstrap --group-id repo-a --root /path/to/repository --dry-run
```

Review source ranges, source digests, candidate classes, and idempotency keys before committing large imports.

## Verified deletion

Only an administrator may request deletion.

```bash
l9-memory delete <record-id> \
  --reason 'verified subject deletion request' \
  --verification-reference ticket-123
```

With projection `none`, the redacted tombstone and deletion receipt complete atomically. With Graphiti or Zep enabled, the record enters `deletion_pending`; the outbox worker uses the stored provider locator to erase the external episode and then completes the receipt.

```bash
l9-memory outbox-run
```

A missing locator, unavailable deletion tool, or provider error leaves the event retryable and prevents a false completion claim.

## MCP stdio

```bash
l9-memory-server --transport stdio
```

The stdio principal is derived from the server working directory and receives no implicit administrator rights. Desktop clients launched outside a repository need explicit local namespace claims:

```bash
export L9_MEMORY_LOCAL_READ_NAMESPACES=l9-graphiti-memory,l9-workspace
export L9_MEMORY_LOCAL_WRITE_NAMESPACES=l9-graphiti-memory
export L9_MEMORY_LOCAL_PROMOTE_NAMESPACES=
export L9_MEMORY_LOCAL_IS_ADMIN=false
```

Use `scripts/write_cursor_config.py` or `scripts/write_claude_config.py`. They write command-only configuration and never copy credentials.

## Remote HTTP MCP

1. Create a JSON token-to-principal mapping outside the repository.
2. Set `L9_MEMORY_AUTH_TOKENS_FILE` to that file.
3. Keep `L9_MEMORY_HTTP_AUTH_REQUIRED=true`.
4. Start:

```bash
l9-memory-server --transport http --host 127.0.0.1 --port 8200
```

Binding to a non-loopback address without authentication is rejected.

## Graphiti projection

```bash
export L9_MEMORY_PROJECTION_BACKEND=http
export GRAPHITI_MCP_URL=https://graphiti.example/mcp
export GRAPHITI_MCP_TOKEN=... # environment or Infisical only
l9-memory-worker --once
```

The adapter discovers the server tool inventory. Current Graphiti tools use `add_memory`, `search_memory_facts`, `search_nodes`, and `delete_episode`. Older `add_episode` and `search_facts` deployments remain supported.

## Zep projection

```bash
python -m pip install '.[zep]'
export L9_MEMORY_PROJECTION_BACKEND=zep
export ZEP_API_KEY=... # environment or Infisical only
l9-memory-worker --once
```

Zep health is `unverified` until a real operation succeeds. Configuration alone is not connectivity proof.

## Ingress recovery

When an adapter cannot reach the canonical service, enqueue the typed write request through the recovery API rather than writing provider or database state directly. Replay later:

```bash
l9-memory recovery-replay --limit 100
```

Replayed requests still pass authorization, consent, admission, idempotency, and canonical persistence.

## Backup and restore

Back up:

- the SQLite database
- active non-secret settings
- external namespace registry
- external principal mapping

Restore procedure:

1. Stop writers and workers.
2. Restore the canonical database.
3. Start with projection `none`.
4. Run `l9-memory health`, `stats`, and representative historical searches.
5. Re-enable the projection.
6. Replay pending outbox events.

Never restore secrets into the repository.

## Failure matrix

| Symptom | Meaning | Action |
|---|---|---|
| write rejected | authorization, consent, or admission denied | inspect receipt reasons |
| write quarantined | safety review required | review as administrator |
| search partial | canonical results exist but an optional strategy failed | inspect strategy failures and repair projection |
| search failed | canonical store failed | stop relying on results and restore store |
| phase lock denied | conflicts exist or retrieval is indeterminate | reconcile and request a new lock |
| projection event retrying | provider unavailable or locator/tool missing | repair provider and rerun worker |
| outbox dead event | retries exhausted | inspect event and replay deliberately after remediation |
| recovery item pending | canonical service unavailable | restore service, then replay |
| prefetch hook error | hydration failed | leave gates off during diagnosis or restore service |

## Release validation

```bash
bash scripts/validate_release.sh
```

The command writes real evidence to `validation/` and exits nonzero on a hard failure. It does not claim live provider, hosted CI, production migration, or credential-rotation proof without those environments.
