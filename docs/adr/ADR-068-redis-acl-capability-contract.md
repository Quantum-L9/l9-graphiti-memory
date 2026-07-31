# ADR-068: Redis ACL Capability Contract for Active Memory

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-068-redis-acl-capability-contract.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

## Status

Accepted (2026-07-28)

Related: ADR-016 (secret and credential boundaries), ADR-021 (testing and adapter conformance), ADR-065

## Context

Consumer applications deploying a dedicated Redis instance for active
memory need to run that instance under least-privilege Redis ACLs
(disabled default user, restricted key/channel patterns, restricted
command set). Without a machine-readable contract, the exact command
set required by the Redis adapter would need to be discovered by trial
and error, and ACL definitions would silently drift from the adapter's
actual behavior as the implementation evolves.

## Decision

Publish `src/l9_graphite_memory/resources/active_memory_redis_capabilities.yaml`
as the single source of truth for:

- required key patterns, parameterized by `{key_prefix}` and
  `{deployment_hash}`
- required channel patterns, parameterized by `{channel_prefix}` and
  `{deployment_hash}`
- required commands, grouped by capability category (connection,
  scalar state, indexes, transactions, scripts, awareness)
- explicitly prohibited commands (`FLUSHALL`, `FLUSHDB`, `CONFIG`,
  `SHUTDOWN`, `DEBUG`, `MODULE`, `MIGRATE`, `REPLICAOF`, `SLAVEOF`,
  `KEYS`, `SAVE`, `BGSAVE`, `BGREWRITEAOF`, `CLUSTER`, `ACL`)

`KEYS` is explicitly prohibited: discovery operations must use bounded
`ZRANGE` queries against role/group sorted-set indexes, never a
full-keyspace scan.

`tools/assurance/render_active_memory_redis_acl.py` renders a
deterministic Redis ACL line from this manifest given a username, key
prefix, channel prefix, and deployment hash. It supports `--check` mode
for CI drift detection and refuses to write a plaintext `--password`
value to any path inside a Git-tracked repository.

If a future adapter change requires a Redis command not present in
this manifest, the manifest and the restricted-ACL conformance test
fixture MUST be updated in the same pull request (enforced by code
review checklist in `RUNBOOK.md`; automated enforcement is deferred —
see MANIFEST.md "Unknowns/Deferred").

## Consequences

- Positive: consumer applications can generate a correct least-
  privilege ACL without inspecting adapter source code.
- Positive: the manifest doubles as living documentation of exactly
  which Redis capabilities this subsystem depends on.
- Negative: this change does not yet include an automated CI check
  that fails if adapter code issues a command outside the manifest
  (that requires a Redis command-tracing test harness against a real
  adapter implementation, which does not yet exist in this
  repository — labeled as a deferred follow-up, not fabricated as
  complete).

## Alternatives Considered

- **Hand-maintained prose documentation of required Redis permissions.**
  Rejected: prose drifts from implementation silently; a machine-
  readable manifest can be consumed by both the ACL renderer and future
  automated drift-detection tooling.
- **Grant `+@all` and rely on network isolation alone.** Rejected:
  contradicts defense-in-depth; a compromised or misconfigured
  consumer process should not be able to run `FLUSHALL` or `CONFIG SET`
  against a shared Redis instance.

## Rejected Alternatives

Hand-maintained prose documentation was rejected because nothing
enforces that it stays synchronized with the adapter's actual command
usage; a machine-readable manifest is the only representation that
both a human operator and an automated renderer/drift-checker can
consume identically. Granting `+@all` behind network isolation alone
was rejected because network isolation is not a substitute for
least-privilege command scoping — a single compromised or
misconfigured consumer process should not be able to run destructive
or topology-altering commands against a shared Redis instance.

## Invariants

`active_memory_redis_capabilities.yaml` is the single source of truth
for required key patterns, channel patterns, commands, and prohibited
commands; `KEYS` is always prohibited in favor of bounded `ZRANGE`
index queries. `render_active_memory_redis_acl.py` never writes a
plaintext `--password` value to any path inside a Git-tracked
repository. Any adapter change requiring a new Redis command must
update this manifest in the same pull request.

## Security Impact

This ADR is itself a security control: it defines the least-privilege
command surface a deployed Redis instance should expose to the
active-memory adapter. The explicit prohibition list
(`FLUSHALL`, `FLUSHDB`, `CONFIG`, `SHUTDOWN`, `DEBUG`, `MODULE`,
`MIGRATE`, `REPLICAOF`, `SLAVEOF`, `KEYS`, `SAVE`, `BGSAVE`,
`BGREWRITEAOF`, `CLUSTER`, `ACL`) bounds the damage a compromised
consumer process can do even with valid credentials. Refusing to write
plaintext passwords into the Git-tracked repository from
`render_active_memory_redis_acl.py` prevents accidental secret
persistence (see Sacred Behavior #7 in `AGENTS.md`).

## Migration Impact

No stored data or schema changes. Consumers deploying active-memory for
the first time can generate an ACL directly from the manifest.
Consumers with an existing, hand-rolled Redis ACL should reconcile it
against the manifest and adopt `render_active_memory_redis_acl.py`
output; this is an additive, opt-in migration with no forced cutover.

## Validation Requirements

`render_active_memory_redis_acl.py --check` must be runnable in CI for
drift detection between the manifest and a previously rendered ACL. The
restricted-ACL conformance test fixture must be updated in the same
pull request as any manifest change that adds or removes a required
command. Tests must confirm the renderer refuses to write a plaintext
password inside a Git-tracked path.

## Rollback Conditions

Revert to hand-maintained prose ACL documentation only if the manifest
format is shown to be an inadequate representation of required Redis
capabilities (e.g. a future capability cannot be expressed
declaratively). Rollback is low-risk since the manifest is documentation-
and tooling-input only; it does not change adapter runtime behavior.

## Supersedes / Superseded By

Supersedes no prior ADR. Not superseded.
