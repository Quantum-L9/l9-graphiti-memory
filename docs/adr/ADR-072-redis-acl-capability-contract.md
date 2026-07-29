# ADR-072: Redis ACL Capability Contract for Active Memory

- Status: Accepted
- Date: 2026-07-28
- Related: ADR-016 (secret and credential boundaries), ADR-021 (testing and adapter conformance), ADR-069

## Context

Consumer applications deploying a dedicated Redis instance for active
memory need to run that instance under least-privilege Redis ACLs
(disabled default user, restricted key/channel patterns, restricted
command set). Without a machine-readable contract, the exact command
set required by the Redis adapter would need to be discovered by trial
and error, and ACL definitions would silently drift from the adapter's
actual behavior as the implementation evolves.

## Decision

Publish `src/l9graphitimemory/resources/active_memory_redis_capabilities.yaml`
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
