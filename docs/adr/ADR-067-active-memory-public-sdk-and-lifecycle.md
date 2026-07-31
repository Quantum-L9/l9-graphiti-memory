# ADR-067: Active-Memory Public SDK and External-Runtime Lifecycle

<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/adr/ADR-067-active-memory-public-sdk-and-lifecycle.md
layer: adr
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

## Status

Accepted (2026-07-28)

Related: ADR-013 (transport abstraction), ADR-038 (SDK/MCP/CLI/HTTP surface), ADR-043 (package wiring and public API governance)

## Context

External consumer applications previously had no supported integration
surface for the active-memory subsystem other than importing adapter
internals directly (e.g. a Redis-backed store class). This coupled
consumer code to internal implementation details, made backend
substitution (in-memory vs. Redis vs. a future backend) a breaking
change for consumers, and left lifecycle concerns (heartbeat
supervision, reconnect, resynchronization, lease expiry) as
undocumented, consumer-reimplemented logic.

## Decision

Introduce `ActiveAgentClient` and `ActiveAgentSession` as the sole
supported public integration surface, exported from
`l9_graphite_memory.active.__all__`. Internal adapter classes (Redis
store/bus implementations, when added) MUST NOT be exported from this
surface; `tools/assurance/check_active_memory_public_api.py` enforces
this in CI.

### Session lifecycle state machine

```
NEW --start()--> REGISTERING --success--> ACTIVE
REGISTERING --failure--> FAILED

ACTIVE --backend interruption--> DEGRADED
ACTIVE --drain()--> DRAINING
ACTIVE --lease rejected--> RE_REGISTERING

DEGRADED --recovery--> RESYNCHRONIZING
DEGRADED --drain()--> DRAINING
DEGRADED --terminal policy--> FAILED

RESYNCHRONIZING --valid lease--> ACTIVE
RESYNCHRONIZING --expired lease--> RE_REGISTERING
RESYNCHRONIZING --failure--> DEGRADED

RE_REGISTERING --success--> RESYNCHRONIZING
RE_REGISTERING --failure--> DEGRADED

DRAINING --unregister success--> CLOSED
FAILED --close()--> CLOSED
```

Enforced invariants:

- Context writes (`replace_context`) are permitted only in `ACTIVE`
  state; all other states reject writes with
  `ActiveMemoryUnavailableError`.
- Heartbeat renewal runs as one supervised background `asyncio.Task`
  per session. Any exception it raises is captured via
  `background_exception()` rather than being silently dropped.
- A lease rejected as expired (`LeaseExpiredError`) triggers
  re-registration with a freshly generated `instance_id`; the
  `agent_id` remains stable across the restart.
- `close()` is idempotent: it may be called multiple times, and it
  unregisters the lease, cancels the heartbeat task, and awaits its
  completion before returning.
- Canonical Graphiti memory operations are outside this state machine
  entirely; active-memory degradation must never block or fail
  canonical memory reads/writes (see ADR-015 failure/degradation
  policy).

## Consequences

- Positive: consumer applications get a tested, documented lifecycle
  instead of re-implementing heartbeat/reconnect logic per
  application.
- Positive: backend substitution (adding a Redis adapter behind the
  same `ActiveStore`/`AwarenessBus` ports) is possible without any
  consumer-visible API change.
- Negative: the state machine intentionally rejects several
  theoretically-useful transitions (e.g. writing while
  `RESYNCHRONIZING`) in favor of strict correctness; consumers needing
  best-effort writes during resynchronization must implement their own
  buffering above this SDK.

## Alternatives Considered

- **Expose adapters directly and document a “best practice” lifecycle
  pattern in prose only.** Rejected: unenforceable; consumers would
  drift into inconsistent, untested lifecycle handling.
- **Synchronous/blocking session API.** Rejected: heartbeat supervision
  fundamentally requires background execution; an async API keeps the
  supervision model explicit and testable with a fake clock.

## Rejected Alternatives

Exposing adapters directly with prose-only lifecycle guidance was
rejected because it is unenforceable — nothing stops a consumer from
importing an internal adapter class or skipping heartbeat supervision,
and drift would only surface as production incidents. A synchronous
API was rejected because heartbeat renewal must run concurrently with
consumer application logic; forcing consumers to manage their own
polling thread would reintroduce exactly the reimplementation problem
this ADR eliminates.

## Invariants

`ActiveAgentClient`/`ActiveAgentSession` are the only supported public
entry points; `l9_graphite_memory.active.__all__` never includes an
adapter implementation class. Every state transition in the lifecycle
diagram is enforced in code, not merely documented: writes outside
`ACTIVE` always raise `ActiveMemoryUnavailableError`, exactly one
supervised heartbeat `asyncio.Task` exists per session, a rejected
lease always regenerates `instance_id` while preserving `agent_id`, and
`close()` is idempotent and awaits full teardown. Active-memory
degradation never propagates into canonical Graphiti memory operations.

## Security Impact

Restricting the public surface to `ActiveAgentClient`/
`ActiveAgentSession` prevents consumers from bypassing lease/heartbeat
enforcement by reaching into adapter internals directly, which would
otherwise let a misbehaving consumer hold a lease past its TTL or write
context without a valid, renewed lease. `tools/assurance/
check_active_memory_public_api.py` enforces this boundary in CI so a
future change cannot silently widen the exported surface.

## Migration Impact

No stored data changes. This ADR defines the first supported public
SDK surface for active-memory; there is no prior public API to migrate
away from. Any future backend addition (beyond in-memory and Redis)
must be introduced behind the existing `ActiveStore`/`AwarenessBus`
ports without a consumer-visible API change, per the stated
consequence of this decision.

## Validation Requirements

The conformance suite (`tests/conformance/active/`) must exercise every
transition in the lifecycle state machine identically across all
`ActiveStore`/`AwarenessBus` implementations. `tools/assurance/
check_active_memory_public_api.py` must run in CI and fail if any
adapter class is added to `l9_graphite_memory.active.__all__`. Tests
must cover heartbeat-task exception capture via
`background_exception()` and idempotent `close()` under repeated calls.

## Rollback Conditions

Revert to direct adapter exposure only if the `ActiveAgentClient`/
`ActiveAgentSession` abstraction is shown to be insufficiently flexible
for a real consumer's lifecycle needs and no incremental extension of
the session API can address it. Rollback would be a breaking change for
every consumer that has adopted the public SDK surface.

## Supersedes / Superseded By

Supersedes no prior ADR. Not superseded.
