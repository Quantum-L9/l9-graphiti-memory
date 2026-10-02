<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: RUNBOOK.md
layer: repository
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-07-27
/L9_META -->

# Runbook

## Install and verify

Checkout-based (ADR-069):

```bash
uv sync --frozen --no-install-project --no-build --extra dev --extra server
source .venv/bin/activate
l9-memory resolve
l9-memory health
```

Published package: `pip install l9-graphite-memory`.

The default canonical store is SQLite at `~/.local/share/l9-memory/memory.sqlite3`. Gate state is under `~/.local/state/l9-memory`.

A SQLite file is authoritative only for processes that can open it. Any deployment where more than one agent, worker, or scheduled job must share memory requires the shared backend (ADR-072):

```bash
export L9_MEMORY_STORE_BACKEND=postgres
# Resolve the DSN from the runtime secret path; never write it into a file in
# this repository. Require TLS with sslmode=require in the DSN.
export L9_MEMORY_POSTGRES_DSN="$(read_secret l9/memory/postgres_dsn)"
l9-memory health
```

Startup fails if `postgres` is selected without a DSN. Never point two deployments at two different SQLite files and treat them as one memory.

### Changing backends

Changing `L9_MEMORY_STORE_BACKEND` points the control plane at a *different* canonical store. Your existing records are not moved — moving them is a separate, evidence-bound operation that this package deliberately does not perform (ADR-072).

Startup refuses when the configured store is empty while a prior ledger still holds records, and names the ledger and its record count (ADR-077):

```
canonical store backend 'postgres' is empty, but this deployment has a prior
canonical ledger that still holds records:
  - sqlite at /root/.local/share/l9-memory/memory.sqlite3 (1482 records)
```

If the switch is a deliberate fresh start, say so:

```bash
export L9_MEMORY_ACKNOWLEDGE_BACKEND_TRANSITION=1
```

The guard only detects a local SQLite ledger, because that is all it can read without credentials. A move between two remote backends is not detected — verify those by hand before cutting over.

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

## Topology publication plans

```bash
l9-memory ingest-topology-plan --plan /bundles/plan --topology-bundle /bundles/topology
l9-memory ingest-topology-plan --plan /bundles/plan --topology-bundle /bundles/topology --apply
```

Preflight is the default and commits nothing. Both inputs are integrity-bound
bundles; validation fails closed on hash, binding, or idempotency-key errors
before any write. Rerunning the same plan after an interruption is the
recovery path — committed operations come back as duplicates. See
`docs/TOPOLOGY_PUBLICATION_ADMISSION.md` and ADR-078.

## Verified deletion

Only an administrator may request deletion.

```bash
l9-memory delete <record-id> \
  --reason 'verified subject deletion request' \
  --verification-reference ticket-123
```

With projection `none`, the redacted tombstone and deletion receipt complete atomically. With Graphiti or Zep enabled, the record enters `deletion_pending`; the outbox worker uses the stored provider locator to erase the external episode and then completes the receipt.

Under the manifest runtime the receipt lists one erase event per target that could hold a copy (`projection_targets`, `projection_event_ids`): every active or shadow target, plus any disabled target that still holds a link. Each target is erased and unlinked independently. The deletion completes only when no link remains, so one failing provider leaves the record `deletion_pending` and retryable while the others are already erased. A disabled target that holds links must stay configured until its erasures drain.

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

Use `l9-memory client cursor install` for Cursor (with `inspect`, `verify`, `status`, and `uninstall` completing the lifecycle) or `scripts/write_claude_config.py` for Claude. Both write command-only configuration and never copy credentials. `scripts/write_cursor_config.py` remains as a thin compatibility wrapper over the canonical `client_config` path. Installs are atomic, preserve unrelated servers, and leave digest-bound backups; `l9-memory client cursor verify` proves the full stdio handshake, tool inventory, and `memory.health` before any live-instantiation claim. See `docs/CURSOR_INSTANTIATION.md`.

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

## Manifest projection runtime

The runtime is chosen explicitly (ADR-084). `legacy`, the default, runs the single `L9_MEMORY_PROJECTION_BACKEND` adapter exactly as above. `manifest` runs every provider target of a compiled projection manifest:

```bash
export L9_MEMORY_PROJECTION_RUNTIME=manifest
export L9_MEMORY_PROJECTION_MANIFEST=config/projections/facts-v8.yaml
export L9_MEMORY_PROJECTION_BACKEND=none   # required: the two modes are exclusive
export GRAPHITI_MCP_URL=https://graphiti.example/mcp
export GRAPHITI_MCP_TOKEN=...              # environment or Infisical only
export ZEP_API_KEY=...                     # environment or Infisical only
l9-memory health
l9-memory-worker --once
```

`facts-v8` declares Graphiti `active` and Zep `shadow`. Each target has a mode:

| Mode | Receives writes | Serves search | Erased on deletion |
|---|---|---|---|
| `active` | yes | yes | yes |
| `shadow` | yes | no | yes |
| `disabled` | no | no | yes, while it holds links |

Manifests carry target names, never credentials. Only a target named `primary` binds the existing `GRAPHITI_MCP_*` or `ZEP_*` settings. An active or shadow target without its settings stops startup; a disabled one starts with no adapter. `L9_MEMORY_PROJECTION_REQUIRED` is a legacy setting and is rejected in manifest mode; mark a target `required: true` in the manifest instead (active targets only).

Every write queues one outbox event per active or shadow target. The worker delivers, retries, and records a link for each target on its own, so a Zep outage never blocks or rolls back Graphiti delivery. `l9-memory health` reports `runtime_mode`, the manifest digests, and each target's mode, configuration, and probe result; disabled targets are not probed.

Search uses active targets only. Strategy labels in receipts are `<target>:<strategy>`, and a failed active strategy makes the receipt `partial` rather than an empty success. Shadow results never alter hits, scores, status, or `stores_*`. The deployed runtime does not query shadow targets at all; shadow measurement is opt-in on `RetrievalPlanner(shadow_measurement=True)` and is reported only in `projection_evidence`.

### Cutover from the legacy runtime

1. Back up the canonical store. Schema 8 rekeys `projection_links` by target identity on first start, keeping every existing row and locator.
2. Stop writers and drain the outbox with `l9-memory outbox-run` until the backlog is zero. Events queued before ADR-084 carry no target identity and fail closed once more than one target exists.
3. Set the manifest settings above and restart the server and worker.
4. Run `l9-memory rebuild-projection --group-id <ns> --target facts:v8:zep:primary` to plan filling the shadow target, then repeat with `--apply`.

Links written by the legacy runtime keep the adapter name as their target identity (`graphiti` for both the HTTP and Zep backends). The manifest runtime does not adopt them: retire and erase events for such a link fail closed and retry, so deleting a record projected before cutover stays `deletion_pending` until a legacy runtime erases that copy. A rebuild under the manifest runtime also projects such records again, leaving the legacy episode beside the new one. Cut over without further steps only when the store holds no legacy links, for example a deployment that ran with `L9_MEMORY_PROJECTION_BACKEND=none`. Adopting legacy links into a manifest target is not implemented yet.

### Rollback

Prefer staying in manifest mode and setting the misbehaving target to `disabled`: nothing new is delivered there, and its existing links remain erasable. Returning to `L9_MEMORY_PROJECTION_RUNTIME=legacy` is safe only after every manifest-identity link has been erased; otherwise those erase events cannot resolve, and the affected deletions stay pending and visible instead of completing. Reverting to a release older than ADR-084 also requires restoring the pre-upgrade backup, since older code cannot write the schema-8 link table.

## Scheduled maintenance

Semantic duplication is admitted on the hot path and resolved later (ADR-071, ADR-075). Maintenance operates only on records that are already canonical.

Always review a plan before applying it:

```bash
l9-memory maintain --group-id repo-a                 # dry run; prints the plan
l9-memory maintain --group-id repo-a --apply
```

Restrict a run with repeatable `--operation` values (`dedupe`, `refine`, `supersede`, `archive`, `reconcile`), and bound it with `--max-records` and `--max-actions`.

The principal needs `MAINTAIN` on the namespace and nothing else. Grant it with `L9_MEMORY_LOCAL_MAINTAIN_NAMESPACES`, or `maintain_namespaces` on a token principal. Do not give a maintenance credential `is_admin`.

Consolidation is additive: it writes a derived record citing its sources and marks the sources `superseded`. Nothing is rewritten in place, so a consolidation judged wrong can be undone by an explicit governance action.

`reconcile` reports contradictions it must not resolve. Those findings recur on every run until someone settles them — that is deliberate, not a loop.

### Nightly scheduled run

`.github/workflows/nightly-maintenance.yml` runs maintenance at 02:00 America/New_York.

GitHub evaluates cron in UTC only, so the workflow fires at both 06:00 and 07:00 UTC (02:00 EDT and 02:00 EST) and `tools/ci/nightly_maintenance_gate.py` admits exactly one. On the spring-forward date, when 02:00 local does not exist, the gate admits the 03:00 firing so the day is not skipped.

The runner is a caller, not a replica. It reaches the shared canonical store over the network (ADR-072) and never creates, caches, uploads, downloads, or commits a database file.

Configure before enabling:

| Setting | Kind | Purpose |
|---|---|---|
| `L9_MEMORY_POSTGRES_DSN` | environment secret | shared canonical store, TLS required |
| `L9_MEMORY_TENANT_ID` | environment variable | tenant the run operates in |
| `L9_MEMORY_MAINTENANCE_NAMESPACES` | environment variable | comma-separated namespaces to maintain |

Scope the credential to the `memory-maintenance` GitHub environment. The workflow grants the run `MAINTAIN` only — it sets no write, promote, or administrator namespaces, and the database role it connects as should be similarly restricted.

Scheduled runs apply. `workflow_dispatch` defaults to a dry run; tick `apply` to make a manual run take effect.

## Rebuilding a projection

Projections are derivations, so they can always be rebuilt from canonical state. Retiring a projection on a provider with no deactivation primitive (Graphiti) removes the projected episode, so restoring an archived record to active leaves it invisible to projection-backed search until it is re-projected (ADR-076):

```bash
l9-memory rebuild-projection --group-id repo-a            # dry run
l9-memory rebuild-projection --group-id repo-a --apply
```

This queues a projection event for every active record with no live projection link, then the outbox worker delivers them. Under the manifest runtime the plan is computed per target (`queued_by_target`); add `--target <target-identity>` to rebuild one target without touching the others. Disabled and unknown targets are rejected. It requires `MAINTAIN` to apply and never touches canonical state. A large rebuild generates provider traffic proportional to the namespace, so run it deliberately.

Every retirement writes a `ProjectionRetirementReceipt` to canonical state recording the mode, locator, and reason. That is what distinguishes a retirement from a privacy erasure — the provider's own log cannot, since both use `delete_episode`.

## Canonical write failure

Canonical ingestion is immediate (ADR-070). When the canonical store is unreachable, the write call raises and the caller must surface that failure. Do not record a local success, and never write provider or database state directly as a fallback. Restore the canonical store, then have the caller retry with the same explicit `idempotency_key` so the retry is recognized as the same operation.

### Draining a retired deferred-ingestion queue

Releases before v2.3 kept an ingress recovery queue under `<state_dir>/write-recovery`. Drain it once, then remove the directory:

```bash
l9-memory drain-legacy-write-queue --dry-run --limit 100
l9-memory drain-legacy-write-queue --limit 100
```

Drained requests still pass authorization, consent, admission, idempotency, and canonical persistence. The command exits non-zero while any item remains unreadable or undeliverable, and preserves those files rather than dropping them.

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
| outbox event stuck PROCESSING | worker died mid-delivery | none; the lease expires after `L9_MEMORY_OUTBOX_LEASE_SECONDS` and the next claim cycle recovers it |
| worker reports `lease_lost` | delivery outran the lease and another worker recovered the event | raise `L9_MEMORY_OUTBOX_LEASE_SECONDS` above the slowest projection call |
| write raised StoreError | canonical store unavailable | restore the store, then retry with the same idempotency key |
| maintenance reports a reconcile action every night | a contradiction is unresolved | settle the conflicting records through governance; the finding is not suppressed until then |
| maintenance action failed with `quarantined` | admission held the derived record for review | review the quarantined candidate as an administrator |
| legacy queue item retained | pre-v2.3 queued write could not be admitted | inspect the preserved file and the reported error |
| prefetch hook error | hydration failed | leave gates off during diagnosis or restore service |

## Constellation Gate health

Inter-node egress uses `constellation-node-sdk` `GateClient` (`CanonicalGateClient`).
Configure identity and authentication on the hosting runtime, never in a request payload:

```bash
export GATE_URL="https://gate.example"
export L9_NODE_NAME="memory-node"
# optional signing: L9_SIGNING_KEY / L9_SIGNING_KEY_ID / L9_SIGNING_ALGORITHM / L9_REQUIRE_SIGNATURE
```

`l9-memory health` reports the canonical store and projection. Gate availability is a
separate `HealthReport.gate` snapshot (`configured` / `healthy` / `status`). Gate
unavailable is `PARTIAL` with reason `gate is unavailable`; it does not mark the
memory core failed. There is no peer URL, destination argument, retry, or
circuit-breaker on dispatch — `send_to_gate` does not authorize those.

## Release validation

```bash
bash scripts/validate_release.sh
```

The command writes real evidence to `validation/` and exits nonzero on a hard failure. It does not claim live provider, hosted CI, production migration, or credential-rotation proof without those environments.
