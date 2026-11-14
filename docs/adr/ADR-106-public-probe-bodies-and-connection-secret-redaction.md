# ADR-106: Public Probe Bodies and Connection-Secret Redaction

**Date:** 2026-11-14
**Decision owner:** Quantum-L9 memory architecture, from the operator decision of 2026-11-14 that audit item U-011 is fixed before the 3.0.0 tag
**Applies to:** `GET /healthz` and `GET /readyz` (`src/l9_graphite_memory/server.py`, `src/l9_graphite_memory/public_probe.py`), `src/l9_graphite_memory/redaction.py`, the canonical store adapters' `health()`, server startup, and `MemorySettings`

## Status

Proposed

The author of this change does not accept its own decision record. Merging
this record on the default branch by the decision owner accepts it; the index
status changes in that same merge.

## Context

`/healthz` and `/readyz` carry no credential. The deployment platform's probe,
the container `HEALTHCHECK` and the runbook all call them unauthenticated, and
on C1 the reverse proxy serves them to the internet. Before this record both
endpoints returned the internal `HealthReport` dump. That dump included the
canonical record count (`store.records`), the outbox backlog and adapter
detail. During a store outage it also included `store.error`: the psycopg2
connect error, which names the database host, port and user.

Three other paths could leak a connection secret. A malformed
`L9_MEMORY_POSTGRES_DSN` put the DSN, password included, into the startup
traceback, both in the `StoreError` message and in the chained driver
exception. `repr(MemorySettings)` printed `postgres_dsn`, `graphiti_mcp_token`,
`zep_api_key` and `auth_tokens`. And with the database stopped, both probes
answered 500 instead of 503, because a rollback on a server-closed connection
raised its own driver error.

## Decision

1. The bodies of the unauthenticated probes are public **allowlists** built by
   `public_probe.py`. They are never a dump of the internal report.
   - A component publishes only its `name`.
   - It publishes the booleans `configured`, `enabled`, `selected`, `required`,
     `healthy` and `ready`, where it reports them.
   - It publishes a `reason` only when that is a stable code matching
     `[a-z][a-z0-9_]*`, such as `store_unavailable`.
   - The `/readyz` `graph` section is `enabled`, `healthy`, `required` and
     `ready`.
   - `readiness.families[].detail` is reduced to `shared_store`.
   - No count, path, URL or exception-derived text is published.
   - Status codes are unchanged. A store that becomes unreachable is a 503 on
     both probes.
2. The full report is available only behind the `/mcp` door, through the
   existing `memory.health` tool. No new public tool is added.
3. Store and connection errors reach a log line or a raised message only
   through `redaction.redact_connection_error`. It strips:
   - `password=` and every other identifying or secret keyword;
   - URI userinfo;
   - secret query parameters;
   - the DSN's own host, port, user and database.

   A failed connect raises `StoreConnectionError` carrying the driver's class
   name only, with no chained driver exception.
4. A server that cannot open its canonical store exits non-zero. Its message
   names `L9_MEMORY_POSTGRES_DSN` and the class of failure, never the value.
   It prints no traceback.
5. Store adapters' `health()` returns a reason code instead of `str(exc)` and
   logs the detail through the redaction path.
6. Every `MemorySettings` field that carries a credential, a connection
   coordinate (host, user, URL, DSN) or an unstructured bag is `repr=False`.
   `model_dump` is unchanged, because callers need the values.

## Alternatives Considered

- Authenticate the probes. Rejected: the platform probe, the `HEALTHCHECK` and
  the runbook have no credential, and the deployment profile's probe path is
  fixed.
- Blocklist the known sensitive keys from the existing dump. A field that a
  future adapter adds would leak by default.
- Switch secret fields to `SecretStr`. That ripples through every call site
  that reads the value. `repr=False` is the repository's existing convention
  (`graph_neo4j_password`).

## Rejected Alternatives

- Keep `str(exc)` and redact only passwords. The host, port and user are
  themselves the internal coordinates that U-011 names.
- A new public `memory.status` tool for the removed detail. It would widen the
  MCP tool set, and `memory.health` already serves an authorized caller.

## Invariants

- An unauthenticated probe body contains no record count, backlog, path, URL
  or exception-derived text.
- Probe status codes and the fields that in-repository consumers read are
  unchanged.
- No log line, raised message or startup output contains a DSN, a password,
  or the store's host, port or user.
- No secret-shaped settings field is visible in `repr`.

## Consequences

Positive: an internet-reachable probe discloses liveness and readiness only. A
field that a future adapter adds cannot reach a public body without a change to
`public_probe.py`, and a new secret-shaped settings field fails a test.

Negative: this is a breaking change to the unauthenticated bodies. They lose
`store.records`, `store.schema_version`, `store.path`, `store.error`,
`outbox_backlog`, projection targets, graph detail beyond four booleans, and
adapter `detail`. An operator reads those through `memory.health` or
`l9-memory readiness`. A failed connect no longer carries the driver
traceback; the redacted message and the class name remain.

## Security Impact

This closes U-011 for the hosted carrier. The authenticated `memory.health`
report still carries provider error text from the Graphiti, Zep and
active-memory probes. The hosted carrier selects none of those providers, so
the residual is package-only and recorded in
`docs/REMAINING_PRODUCTION_PROOF.md`.

## Migration Impact

There is no schema, store or configuration change. In this repository, every
consumer of the probe bodies reads only fields that remain: RUNBOOK section C
step 6, the carrier proof, and the multiprocess, OAuth, live-readiness,
active-memory and graph tests. The deployment profile and the `HEALTHCHECK`
read the status code only. A consumer outside this repository that reads a
removed field must switch to `memory.health`.

## Validation Requirements

- `tests/unit/test_secret_disclosure.py` covers:
  - hostile keyword, URI and broken DSNs;
  - the real driver path;
  - the server process's stdout and stderr;
  - the healthy and store-down public bodies;
  - the 503 on a store lost mid-probe;
  - the settings walker.
- The carrier tests `test_unauthenticated_probes_disclose_no_count_or_store_coordinate`
  and `test_a_failed_start_with_an_unusable_dsn_logs_no_part_of_it` run in full
  in `release-container.yml`.
- `bash scripts/validate_release.sh` must pass.

## Rollback Conditions

Revert this record together with `public_probe.py`, `redaction.py` and their
call sites. Status codes and consumer fields are identical either way, so no
deployment or profile change is needed. A rollback re-opens U-011.

## Supersedes / Superseded By

Amends the probe statements of ADR-038 and ADR-097. The probes stay
unauthenticated, and ADR-097's families keep their semantics. Their public
representation is now this allowlist. Supersedes none.
