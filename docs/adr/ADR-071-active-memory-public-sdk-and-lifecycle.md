# ADR-071: Active-Memory Public SDK and External-Runtime Lifecycle

- Status: Accepted
- Date: 2026-07-28
- Related: ADR-013 (transport abstraction), ADR-038 (SDK/MCP/CLI/HTTP surface), ADR-043 (package wiring and public API governance)

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
`l9graphitimemory.active.__all__`. Internal adapter classes (Redis
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
