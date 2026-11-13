<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: RUNBOOK.md
layer: repository
owner: memory-control-plane
status: active
version: 2.3.0
updated: 2026-11-13
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
# this repository. Require TLS with sslmode=require in the DSN whenever the
# database is reached over a network (the on-host C1 container is the stated
# exception; see "Hosted Memory on C1").
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

Stdio MCP is the supported agent transport of the 2.5.0 operational release and of `main`, and stays supported for local use in the ADR-098 candidate and the 3.0.0 target; it is not the multi-machine deployment. Its principal is established once at startup, server-side, in three tiers (ADR-083): the human door (`L9_MEMORY_HUMAN_DOOR_SECRET` set) yields an administrator principal; otherwise the agent door (`L9_MEMORY_AGENTS_DOOR_SECRET` set) yields the principal of a verified signed agent assertion and canonical identity assertion; otherwise the principal comes from the server working directory, with no administrator rights unless `L9_MEMORY_LOCAL_IS_ADMIN` (or `L9_MEMORY_LOCAL_IS_GLOBAL_ADMIN`) is set true. Desktop clients launched outside a repository need explicit local namespace claims:

```bash
export L9_MEMORY_LOCAL_READ_NAMESPACES=l9-graphiti-memory,l9-workspace
export L9_MEMORY_LOCAL_WRITE_NAMESPACES=l9-graphiti-memory
export L9_MEMORY_LOCAL_PROMOTE_NAMESPACES=
export L9_MEMORY_LOCAL_IS_ADMIN=false
```

Use `l9-memory client cursor install` for Cursor (with `inspect`, `verify`, `status`, and `uninstall` completing the lifecycle) or `scripts/write_claude_config.py` for Claude. Both write command-only configuration and never copy credentials. `scripts/write_cursor_config.py` remains as a thin compatibility wrapper over the canonical `client_config` path. Installs are atomic, preserve unrelated servers, and leave digest-bound backups; `l9-memory client cursor verify` proves the full stdio handshake, tool inventory, and `memory.health` before any live-instantiation claim for the local stdio entry. It proves nothing about remote HTTP. See `docs/CURSOR_INSTANTIATION.md`.

## Remote HTTP MCP

**Status (2026-11-13).** The target is Memory 3.0.0: one `MemoryService`
hosted on the operator's Hetzner C1 environment, reached by authorized agents
over authenticated HTTPS MCP, backed by a new, empty PostgreSQL 16 database
(ADR-038, ADR-100). It is **not deployed**, and no consumer is bound to it.

The hosted door is Auth0 OAuth only (ADR-100, 2026-10-27). Signed-agent HMAC
and static bearer are not hosted doors and are not fallbacks, and Memory stdio
is not a rollback of the hosted service. The OAuth mode does not exist in this
repository yet (issue #108), so the hosted carrier refuses to start in every
auth mode. The two modes described below remain in the package for local use;
neither is how C1 is reached. What exists depends on the code you run:

| Code | HTTP server |
|---|---|
| 2.5.0, 2.6.0, `main@441b741` | not qualified for remote agents: one JSON object per `POST /mcp`; `initialize` always answers `2024-11-05`; no negotiation, `MCP-Protocol-Version`, `Origin` or `Accept` handling; `notifications/initialized` gets `200 {"status":"ok"}` instead of `202`; static bearer tokens only. With authentication disabled, loopback HTTP serves the stdio principal, which is the administrator when `L9_MEMORY_HUMAN_DOOR_SECRET` is set, so never disable authentication there. |
| ADR-098 in the 3.0.0 release candidate (source 3.0.0; untagged) | stateless Streamable HTTP (`2025-11-25`, `2025-06-18`) with `bearer` (default) or `signed-agent` authentication; contract in `docs/REMOTE_MCP_CONTRACT.md`; not an accepted release, and neither mode is a hosted door (ADR-100) |

On every version, `GET /healthz`, `GET /readyz` and FastAPI's default `/docs`,
`/redoc` and `/openapi.json` are served without authentication, and there is no
TLS in process.

### Bearer mode (local development and service principals)

Not a hosted door (ADR-100); the hosted carrier refuses it.

1. Create a JSON token-to-principal mapping outside the repository
   (`config/auth_tokens.json.example` shows the shape).
2. Set `L9_MEMORY_AUTH_TOKENS_FILE` to that file.
3. Keep `L9_MEMORY_HTTP_AUTH_REQUIRED=true`.
4. Start on loopback:

```bash
l9-memory-server --transport http --host 127.0.0.1 --port 8200
```

Binding to a non-loopback address without authentication is rejected. A
bearer token is a shared string mapped to configured claims; it is **not** an
agent identity, and a token's principal can carry `is_admin` and
`is_global_admin`. Do not use bearer mode for remote agents.

### Signed-agent mode (ADR-098 candidate only)

ADR-100 retired this as the hosted door: it is not how C1 is reached, the
hosted carrier refuses it, and it is not a fallback for OAuth. What follows
describes the mode as the package implements it.

Remote agents authenticate with the same signed evidence the stdio agent door
verifies, re-verified on every request (ADR-098, `docs/REMOTE_MCP_CONTRACT.md`):

1. Provision the server-side registry outside the repository:
   `L9_MEMORY_AGENT_SIGNING_KEYS_JSON` (`{agent_id: key}`) and
   `L9_MEMORY_AGENT_GRANTS_JSON` (`{agent_id: grant}`). Every registered agent
   needs a grant, and no grant may set `is_admin`; the server refuses to start
   otherwise. Administrator work stays on the local human door.
2. `export L9_MEMORY_HTTP_AUTH_MODE=signed-agent`; optionally
   `L9_MEMORY_HTTP_ALLOWED_ORIGINS` and
   `L9_MEMORY_HTTP_AGENT_ASSERTION_MAX_TTL_SECONDS` (default 3600).
3. Start `l9-memory-server --transport http` behind TLS termination.

Clients send `Authorization: Bearer <agent assertion>`, `L9-Identity-Assertion`
(base64url sealed JSON), `L9-Identity-Assertion-HMAC`, and
`MCP-Protocol-Version` on every request. A credential is reusable until it
expires; it is not single-use. One server runs one mode: a `signed-agent`
server does not accept bearer tokens, so bearer clients such as the
TypeScript client cannot use it. Roll back with
`L9_MEMORY_HTTP_AUTH_MODE=bearer`, or stop the HTTP transport.

### Hosted Memory on C1: operator procedure (3.0.0 target)

**Nothing in this section has been run on C1.** It is written for the operator
to run later; Docker on C1 was out of reach when it was written (2026-11-13).
Each step carries one mark for the strongest evidence behind it:

- **[repo]** — the fact the step relies on is verified in this repository
  (file named in the step).
- **[l9-deploy]** — the step relies on l9-deploy behaviour as verified by the
  campaign coordinator in `Quantum-L9/l9-deploy@c89be89`; not re-verified here.
- **[not run on C1]** — written from documentation and from a rehearsal on a
  throwaway local Docker 29.9.2 engine (2026-11-13); no evidence from C1.

No mark means the step ran on C1. Placeholders in `<ANGLE_BRACKETS>` are values
this repository does not record; they are collected under
[Operator must confirm](#operator-must-confirm). No command below contains or
prints a secret value.

Fixed names used throughout:

| Thing | Name | Source |
|---|---|---|
| Host | C1, `46.62.243.82`, SSH as `root` | `.l9/deployment.yaml` |
| Docker network | `l9-runtime` (external, shared) | l9-deploy |
| Release container | `l9-graphiti-memory-app-1` | l9-deploy: `<project.id>-app-1` |
| Service port | `127.0.0.1:8200` on the host, `8200` in the container | `.l9/deployment.yaml` |
| Database container | `l9-graphiti-memory-postgres` | chosen here |
| Database volume | `l9-graphiti-memory-postgres-data` | chosen here |
| Database role and database | `l9_memory` / `l9_memory` | chosen here |
| Database image | `postgres:16@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97` | `.l9/deployment.yaml` (the image the backup and restore test run) |
| Secret store | Infisical project `l9-graphiti-memory`, environment `prod` | `.l9/deployment.yaml` |
| Backups | `/srv/l9/backups/l9-graphiti-memory/<ENVIRONMENT>/<request_id>.sql.gz` | `.l9/deployment.yaml` |

The database is a dedicated PostgreSQL 16 container on `l9-runtime` with a named
volume and **no published host port**. It is not C1's existing loopback database
on `127.0.0.1:5432`, which a container cannot reach. Its host name resolves only
on `l9-runtime`, so every command that talks to it runs inside a container on
that network or through `docker exec` into the database container; a client on
the host with the service's DSN cannot resolve the name. l9-deploy does not
provision it (`services.postgres.mode: external`).

Nothing is imported: the database starts empty (ADR-100), and no ledger, graph,
Redis state or older backup is loaded into it.

#### Before you start

The hosted door is Auth0 OAuth only (ADR-100). The 3.0.0 carrier in this
repository has no OAuth mode yet, so its entrypoint exits with status 64 on
every start (`Dockerfile`, `l9-memory-carrier`); issue #108 adds the mode and
the `v3.0.0` tag is not cut before it lands. **Sections A and B can be done at
any time. Do not start section C until the tag exists and issue #108 is
closed**: C stops the legacy service, and a carrier that cannot start would
leave the port empty.

#### A. Preconditions on C1

Run on C1 as `root`. Stop at the first check that fails.

1. **[not run on C1]** Docker answers:

   ```bash
   docker info --format '{{.ServerVersion}} {{.DockerRootDir}}'
   ```

2. **[l9-deploy]** Compose is 2.30.0 or newer. l9-deploy refuses the host
   otherwise, and with `host.docker: verify` it never installs or upgrades
   Docker, so an older Compose must be upgraded by the operator first:

   ```bash
   docker compose version --short
   ```

3. **[not run on C1]** Free disk for the image (about 650 MB), the data volume
   and the dumps. Use the `DockerRootDir` printed in step 1:

   ```bash
   df -h <DOCKER_ROOT_DIR> /srv
   ```

4. **[l9-deploy]** The shared network exists. l9-deploy creates it at deploy
   time if it is missing, but the database must join it before the first
   deploy:

   ```bash
   docker network inspect l9-runtime --format '{{.Name}} {{.Driver}} {{.Scope}}'
   ```

   If it is missing, see "Operator must confirm" before creating it with
   `docker network create l9-runtime`.

5. **[not run on C1]** The names this procedure creates are free. Both commands
   must print nothing:

   ```bash
   docker ps -a --filter 'name=^l9-graphiti-memory-postgres$' --format '{{.Names}}'
   docker volume ls --filter 'name=^l9-graphiti-memory-postgres-data$' --format '{{.Name}}'
   ```

#### B. Provision the PostgreSQL 16 container (once)

Run on C1 as `root`, in one interactive `bash` session. The two passwords are
generated into shell variables by command substitution, passed on by variable
name or on standard input, and never appear on a command line, in shell
history or on the terminal.

1. **[not run on C1]** Keep this session out of shell history and make new
   files private:

   ```bash
   set +o history
   umask 077
   IMAGE='postgres:16@sha256:9e2cf6287f25c3151f4c9421ccce2b17f3e60061c111a29165e0d2cdd9ff0a97'
   docker pull "$IMAGE"
   ```

2. **[not run on C1]** Start the container: pinned image, on `l9-runtime`,
   named volume at the image's data path, restart policy, and no `-p` or
   `--publish`. `-e POSTGRES_PASSWORD` without a value forwards the variable
   from the shell. It is the bootstrap superuser password and is removed in
   step 4:

   ```bash
   POSTGRES_PASSWORD="$(openssl rand -hex 32)"
   export POSTGRES_PASSWORD
   docker run -d \
     --name l9-graphiti-memory-postgres \
     --network l9-runtime \
     --restart unless-stopped \
     --volume l9-graphiti-memory-postgres-data:/var/lib/postgresql/data \
     -e POSTGRES_PASSWORD \
     "$IMAGE"
   unset POSTGRES_PASSWORD
   ```

3. **[not run on C1]** Wait until it accepts connections:

   ```bash
   until docker exec l9-graphiti-memory-postgres pg_isready -U postgres -q; do sleep 1; done
   ```

4. **[not run on C1]** Create the service's own role and database, and remove
   the superuser's password. Administration from here on goes through
   `docker exec` and the container's local socket, which the image trusts; no
   superuser can log in over the network. The SQL travels on standard input
   (`printf` is a shell builtin), not on a command line:

   ```bash
   APP_PASSWORD="$(openssl rand -hex 32)"
   printf "CREATE ROLE l9_memory LOGIN PASSWORD '%s';\nCREATE DATABASE l9_memory OWNER l9_memory;\nALTER ROLE postgres PASSWORD NULL;\n" "$APP_PASSWORD" \
     | docker exec -i l9-graphiti-memory-postgres psql -v ON_ERROR_STOP=1 -q -U postgres -d postgres
   ```

5. **[not run on C1]** Put the DSN straight into Infisical as
   `L9_MEMORY_POSTGRES_DSN` (project `l9-graphiti-memory`, environment `prod`).
   The value goes through a root-only file on tmpfs that the Infisical CLI
   reads (`NAME=@file`), so it is never an argument and never displayed. Do
   not `cat` the file. The DSN is written in libpq keyword form; the generated
   password is hexadecimal, so it needs no quoting:

   ```bash
   install -m 600 /dev/null /run/l9-memory-dsn
   printf 'host=l9-graphiti-memory-postgres port=5432 dbname=l9_memory user=l9_memory password=%s' "$APP_PASSWORD" > /run/l9-memory-dsn
   unset APP_PASSWORD
   infisical secrets set L9_MEMORY_POSTGRES_DSN=@/run/l9-memory-dsn --env=prod --projectId=<INFISICAL_PROJECT_ID>
   rm -f /run/l9-memory-dsn
   set -o history
   ```

   **Known limitation, accepted for this release by the campaign coordinator
   (2026-11-13):** the DSN carries no `sslmode=require`. The image starts
   without a server certificate, and the connection never leaves the
   `l9-runtime` bridge on this host. `l9-runtime` is shared, so other
   containers on it can reach port 5432; the role password is the only
   control. No other project should be attached to the database container's
   network alias (checked in step 6).

6. **[not run on C1]** Verify it is up, restarts by policy, sits only on
   `l9-runtime` and publishes nothing:

   ```bash
   docker inspect l9-graphiti-memory-postgres --format \
     '{{.State.Status}} restart={{.HostConfig.RestartPolicy.Name}} ports={{json .HostConfig.PortBindings}} networks={{range $k, $v := .NetworkSettings.Networks}}{{$k}} {{end}}'
   docker port l9-graphiti-memory-postgres
   docker exec l9-graphiti-memory-postgres psql -U postgres -d l9_memory -tAc 'select version()'
   ```

   Expected: `running restart=unless-stopped ports={} networks=l9-runtime`, no
   output from `docker port`, and a `PostgreSQL 16.` version line. Then list
   what else is on the network, and confirm no other container answers to the
   name `l9-graphiti-memory-postgres`:

   ```bash
   docker network inspect l9-runtime --format '{{range .Containers}}{{.Name}}{{"\n"}}{{end}}'
   docker ps -a --filter 'network=l9-runtime' --format '{{.Names}}\t{{.Image}}'
   ```

7. **[repo]** There is no schema step. The database stays empty until the
   service first starts: `PostgresStore` creates its tables, `memory_records`
   included, with `CREATE TABLE IF NOT EXISTS` under an advisory lock and
   records the schema version in `schema_migrations`
   (`src/l9_graphite_memory/adapters/postgres_store.py`). The profile declares
   `migrations.enabled: false` for that reason.

#### C. Cut over from the legacy service

Port 8200 on C1 is held by the legacy 2.2.0 systemd service
(`.l9/deployment.yaml`). This repository does not record that unit's name.
The order matters: the new container cannot bind `127.0.0.1:8200` while the
legacy unit holds it, and from step 3 until step 6 passes, agents have no
hosted memory.

1. **[not run on C1]** Name the legacy unit from the process that holds the
   port, and keep its definition for the rollback:

   ```bash
   ss -ltnp 'sport = :8200'
   systemctl status <PID_FROM_SS> --no-pager
   systemctl cat <LEGACY_MEMORY_UNIT> > /root/<LEGACY_MEMORY_UNIT>.before-cutover
   ```

2. **[repo]** Confirm the release can be requested: sections A and B are done,
   `L9_MEMORY_POSTGRES_DSN` and the OAuth settings issue #108 names are in
   Infisical `prod`, the `v3.0.0` tag exists, and the host key in
   `.l9/deployment.yaml` has been re-verified against C1 over a trusted channel
   (the profile records it as an evidence lead only).

3. **[not run on C1]** Stop and disable the legacy unit:

   ```bash
   systemctl disable --now <LEGACY_MEMORY_UNIT>
   systemctl is-active <LEGACY_MEMORY_UNIT>
   systemctl is-enabled <LEGACY_MEMORY_UNIT>
   ```

   Expected: `inactive` and `disabled`.

4. **[not run on C1]** Confirm the port is free. This must print no listener:

   ```bash
   ss -ltn 'sport = :8200'
   ```

5. **[repo]** Request the release: dispatch the release workflow on the tag,
   then approve the protected environment in l9-deploy when it asks
   (`.github/workflows/release-container.yml` accepts only a `v<MAJOR.MINOR.PATCH>`
   tag run and the `production` target):

   ```bash
   gh workflow run release-container.yml --repo Quantum-L9/l9-graphiti-memory --ref v3.0.0 -f environment=production
   ```

6. **[not run on C1]** Confirm the new service is the one answering. All four
   must hold:

   ```bash
   docker ps --filter 'name=^l9-graphiti-memory-app-1$' --format '{{.Names}} {{.Status}} {{.Ports}}'
   ss -ltnp 'sport = :8200'
   curl -fsS http://127.0.0.1:8200/readyz | python3 -c 'import json, sys; d = json.load(sys.stdin); print(d["package_version"], d["status"])'
   docker inspect l9-graphiti-memory-app-1 --format '{{index .Config.Labels "org.opencontainers.image.revision"}}'
   ```

   Expected: the container is `Up` and healthy with `127.0.0.1:8200->8200/tcp`;
   the listener on 8200 belongs to Docker, not to the legacy process;
   `/readyz` answers 200 with `package_version` `3.0.0` (the legacy service is
   2.2.0); and the revision label equals the commit of the tag
   (`git rev-parse 'v3.0.0^{commit}'` in a checkout). Then check the public
   route through the host's existing proxy:

   ```bash
   curl -fsS https://memory.quantumaipartners.com/readyz >/dev/null && echo ok
   ```

**Manual rollback of a failed first deploy.** **[l9-deploy]** A first release
has no previous release, so l9-deploy has nothing to roll back to and leaves
the new container in place even with `release.automatic_rollback: true`.
**[not run on C1]** Restore the legacy service by hand:

```bash
docker logs --tail 200 l9-graphiti-memory-app-1 > /root/l9-graphiti-memory-first-deploy.log 2>&1
docker rm -f l9-graphiti-memory-app-1
ss -ltn 'sport = :8200'
systemctl enable --now <LEGACY_MEMORY_UNIT>
systemctl is-active <LEGACY_MEMORY_UNIT>
ss -ltnp 'sport = :8200'
curl -fsS http://127.0.0.1:8200/<LEGACY_HEALTH_PATH>
```

Expected: after `docker rm`, no listener on 8200; after `enable --now`,
`active`, with the legacy process holding the port again. Only the one named
container is removed. The database container and its volume stay; anything
written to PostgreSQL during the window is not visible to the legacy service,
which keeps its own store. Leave `l9-graphiti-memory-postgres` running for the
next attempt.

#### D. Backup, verify and restore test

**[repo]** The three commands are `backup.command`, `backup.verify_command` and
`backup.restore_test_command` in `.l9/deployment.yaml`, pinned by
`tests/deployment/carrier/test_deployment_profile.py`:

- **Backup.** The release container splits its own DSN into libpq variables;
  a `pg_dump` from the pinned PostgreSQL 16 image runs on `l9-runtime` with
  those variables forwarded by name; the gzip dump and its `.sha256` are
  written under `/srv/l9/backups/`. The host's `l9-postgres-backup` and its
  unpinned `pg_dump` are not used. The release container must be running: it
  is the only place the DSN is read from.
- **Verify.** `/usr/local/sbin/l9-backup-verify` on the newest dump (non-empty,
  checksum matches, gzip intact).
- **Restore test.** The newest verified dump is loaded into a throwaway
  PostgreSQL 16 container with `--network none` and must contain the
  `memory_records` table. It never connects to the live database.

**[l9-deploy]** They run on C1 over SSH from l9-deploy's backup-verify
workflow, not from a deployment. The executor joins each argument with
`shlex.join`, so the multi-line backup script arrives intact, and
`l9-backup-verify` checks a `.sha256` that records the dump's absolute path,
which is the form `backup.command` writes. A deployment does not run them:
this profile has migrations off and no persistent volume, so a deployment plan
contains no pre-deploy backup step.
Invoke `<L9_DEPLOY_BACKUP_VERIFY_WORKFLOW>` for project `l9-graphiti-memory`.

**[not run on C1]** A pass looks like this:

- backup exits 0 and prints the dump's path,
  `/srv/l9/backups/l9-graphiti-memory/<ENVIRONMENT>/<request_id>.sql.gz`;
- verify exits 0 and prints `<that path>: OK`;
- the restore test exits 0, prints the same `OK` line, and leaves no container
  named `l9-restore-l9-graphiti-memory-<ENVIRONMENT>` behind;
- on C1, both files exist and are readable by `root` only:

  ```bash
  ls -l /srv/l9/backups/l9-graphiti-memory/<ENVIRONMENT>/
  ```

A backup that fails leaves no `.sql.gz` for that request: a wrong password, a
stopped release container or an interrupted dump each end the command non-zero
before the file is moved into place.

**Recovery point.** Nothing in this repository schedules a backup, and a
deployment does not take one. The recovery point is the last time the
operator ran the backup-verify workflow; until the operator schedules it, it
is unbounded. There is no WAL archiving and no point-in-time recovery. The
dumps sit on the same host as the database, so losing C1 loses both unless the
operator copies them elsewhere. Nothing here prunes old dumps.

**Restoring the live database** (**[not run on C1]**; every agent loses hosted
memory from the `docker stop` until `/readyz` passes). The current database is
renamed, not dropped, so the step can be undone:

```bash
f=/srv/l9/backups/l9-graphiti-memory/<ENVIRONMENT>/<request_id>.sql.gz
/usr/local/sbin/l9-backup-verify "$f"
docker stop l9-graphiti-memory-app-1
docker exec l9-graphiti-memory-postgres psql -v ON_ERROR_STOP=1 -q -U postgres -d postgres \
  -c 'ALTER DATABASE l9_memory RENAME TO l9_memory_before_restore' \
  -c 'CREATE DATABASE l9_memory OWNER l9_memory'
gzip -dc "$f" | docker exec -i l9-graphiti-memory-postgres psql -v ON_ERROR_STOP=1 -q -U l9_memory -d l9_memory >/dev/null
docker start l9-graphiti-memory-app-1
curl -fsS http://127.0.0.1:8200/readyz >/dev/null && echo ready
```

Dumps are taken with `--no-owner`, so loading as `l9_memory` makes the service
role the owner of every table. Drop `l9_memory_before_restore` only after the
restored service has been checked, by its exact name.

**If the service fails.** A failed MemoryService or proxy affects every
connected agent, and there is no fallback door: Memory stdio is not a rollback
of the hosted service (ADR-100). A local stdio entry writes to its own local
store, so nothing written there is in the shared memory.

#### E. The older database on C1 (optional, not part of this deployment)

The operator has stated (2026-11-13) that an older database on C1 is stale and
already backed up. Removing it is optional housekeeping. No step above depends
on it, and nothing is imported from it. This repository does not record its
container or volume name, so name both exactly before removing anything:

```bash
docker ps -a --format '{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
docker inspect <OLD_DB_CONTAINER> --format '{{range .Mounts}}{{.Type}} {{.Name}} {{.Destination}}{{"\n"}}{{end}}'
docker ps -a --filter 'volume=<OLD_DB_VOLUME>' --format '{{.Names}}'
```

**[not run on C1]** Proceed only if `<OLD_DB_CONTAINER>` is not
`l9-graphiti-memory-postgres`, is not the database other services on C1 use
through `127.0.0.1:5432`, and the last command lists that container alone:

```bash
docker stop <OLD_DB_CONTAINER>
docker rm <OLD_DB_CONTAINER>
docker volume rm <OLD_DB_VOLUME>
```

`docker volume rm` refuses a volume that a container still uses; treat a
refusal as a stop, not as something to force. Never use `docker system prune`,
`docker volume prune`, `-f` or a wildcard here: C1 is shared, and those remove
other services' state.

#### Operator must confirm

| Placeholder or assumption | What to confirm |
|---|---|
| `<LEGACY_MEMORY_UNIT>` | The systemd unit of the legacy 2.2.0 service holding port 8200 (found in C step 1). |
| `<LEGACY_HEALTH_PATH>` | A path the legacy service answers, to confirm a rollback. |
| `<INFISICAL_PROJECT_ID>` | The id of Infisical project `l9-graphiti-memory`; that the Infisical CLI is installed and authenticated where step B5 runs, and that its version accepts `NAME=@file` (newer CLIs spell the command `infisical sm secrets set`). Without it, set the secret by another route that does not display it. |
| `<ENVIRONMENT>` | The environment name l9-deploy substitutes into backup paths and the restore container name (`production`, the target name, is expected). |
| `<L9_DEPLOY_BACKUP_VERIFY_WORKFLOW>` | The exact l9-deploy workflow and inputs that run backup, verify and restore test, and who schedules it. |
| `<OLD_DB_CONTAINER>`, `<OLD_DB_VOLUME>` | The stale database's exact container and volume, if it is removed at all. |
| `<DOCKER_ROOT_DIR>` | Printed by A step 1. |
| `l9-runtime` created by hand | That a plain `docker network create l9-runtime` is the network l9-deploy expects, if it does not exist yet. |
| Network alias | That no other project's container is attached to `l9-runtime` under the name `l9-graphiti-memory-postgres` (B step 6). The connection has no TLS; the role password is the only control. |
| Proxy route | That the host's existing Caddy already routes `memory.quantumaipartners.com` to `127.0.0.1:8200`; l9-deploy never edits it (`ingress.mode: external`). |
| After a manual rollback | That l9-deploy accepts a new first release after the container was removed by hand. |

### Client adoption

Server availability is not consumer adoption. Each consumer proves its own
configuration in its own repository:

- **Cursor-Governance** seals the agent HTTP path today (its ADR-0031 and
  `CANONICAL_LAW.md` §8.5). Cursor and Claude Code agents governed there need
  an authorized consumer campaign before using the remote service.
- **Claude Code** documents `headersHelper`, which can mint fresh headers at
  session start, on reconnect and after `401`/`403`. That is documented client
  functionality, not demonstrated acceptance.
- **Cursor** documents static `headers` with environment expansion and no
  refresh hook; a short-lived credential must be refreshed outside the IDE.
  Not qualified.

### Proof boundaries

Proven by the candidate's tests: the Streamable HTTP wire contract over real
TCP, the signed-agent negative suite, receipt shapes, the installed wheel's
HTTP entry point, and startup refusal of an administrator agent grant in
signed-agent and auth-disabled modes, including by the installed wheel,
against an in-memory store (suite) and SQLite (installed-wheel proof). Not
proven: HTTP against PostgreSQL, the four lifecycle operations ADR-082
(2026-10-14) lists, any C1 deployment, and any consumer's remote
configuration.

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
| `L9_MEMORY_POSTGRES_DSN` | environment secret | shared canonical store; TLS required when reached over a network (on-host C1 container excepted, see "Hosted Memory on C1") |
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

This section is for a local SQLite ledger. The hosted store on C1 is PostgreSQL;
its backup, verification, restore test and live restore are in
[Hosted Memory on C1, section D](#d-backup-verify-and-restore-test).

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
| readiness `failed`, reason `active_store is required but not configured` | the deployment requires active memory and `L9_MEMORY_ACTIVE_BACKEND` is `none` | bind the Redis backend (below) or drop `L9_MEMORY_ACTIVE_REQUIRED` |
| readiness `failed`, reason `active_store is unhealthy` | the Redis probe could not PING, write a scalar or a sorted set | restore Redis or its ACL; canonical memory is unaffected meanwhile |
| session state `degraded` | heartbeat renewals failed past the threshold | none; the session resynchronizes and re-registers when Redis returns |

## Active memory (Redis)

Presence, leases, context and awareness shared by concurrently running agents
are composed beside canonical memory (ADR-097). Select the backend, the
deployment identity (ADR-065) and exactly one credential source (ADR-066):

```bash
export L9_MEMORY_ACTIVE_BACKEND=redis
export L9_MEMORY_ACTIVE_REQUIRED=true
export L9_MEMORY_ACTIVE_DEPLOYMENT_ID=fleet-production
export L9_MEMORY_ACTIVE_TRUST_DOMAIN=my-organization
export L9_MEMORY_ACTIVE_ENVIRONMENT=production
# Name the variable (or mounted file) that holds the URL; never the URL itself.
export L9_MEMORY_ACTIVE_REDIS_URL_ENV=FLEET_REDIS_URL
l9-memory readiness
```

A consumer process obtains its client from the composed runtime
(`build_runtime().active_memory.client()`, see `docs/ACTIVE_MEMORY_SDK.md`).
Startup refuses a placeholder identity in production, an ambiguous or missing
credential source, and a lease TTL that does not exceed the heartbeat
interval. An unreachable server is not a startup failure: readiness reports
it, and canonical memory keeps working.

## Full-capability readiness

`l9-memory readiness` and `GET /readyz` report five capability families on
their own evidence: `canonical` (always required), `projection` (required
when enabled), `graph` (`L9_MEMORY_GRAPH_REQUIRED`), `active_store` and
`awareness_bus` (`L9_MEMORY_ACTIVE_REQUIRED`). Each carries `selected`,
`required`, `healthy` and `ready`; `ready` is the aggregate, and
`full_capability` is true only when every family is selected and healthy. A
required family that is absent or unhealthy is `failed`, never green; an
optional unhealthy family is `partial`. `l9-memory health` and `memory.health`
keep the canonical-plus-projection shape consumers already bind to.

For the consumer-selected full-capability shared deployment (PostgreSQL
canonical store, Graphiti projection plus Neo4j graph intelligence, Redis
active store plus awareness bus) set every `*_REQUIRED` flag and require
`full_capability: true` before declaring the deployment live.

`full_capability` is a stricter, optional profile. It is not a prerequisite
for basic shared canonical memory: a deployment selecting only the PostgreSQL
canonical store, with projection, graph intelligence and active memory left at
`none`, is judged on the `canonical` family alone.

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
