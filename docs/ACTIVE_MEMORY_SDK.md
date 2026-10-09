<!-- L9_META
l9_schema: 1
repo: Quantum-L9/l9-graphiti-memory
path: docs/ACTIVE_MEMORY_SDK.md
layer: documentation
owner: memory-control-plane
status: active
version: 2.2.0
updated: 2026-07-22
/L9_META -->

# Active Memory SDK Guide

This guide documents the only supported integration surface for the
active-memory subsystem: `ActiveAgentClient` and `ActiveAgentSession`,
exported from `l9_graphite_memory.active`.

## Constructing a client

The runtime factory builds the client from settings (ADR-097). A consumer
selects the backend, the deployment identity and exactly one ADR-066
credential source, and never instantiates an adapter:

```bash
export L9_MEMORY_ACTIVE_BACKEND=redis
export L9_MEMORY_ACTIVE_REQUIRED=true            # readiness fails without it
export L9_MEMORY_ACTIVE_DEPLOYMENT_ID=my-application-production
export L9_MEMORY_ACTIVE_TRUST_DOMAIN=my-application
export L9_MEMORY_ACTIVE_ENVIRONMENT=production
# The name of the variable that holds the Redis URL, not the URL itself.
export L9_MEMORY_ACTIVE_REDIS_URL_ENV=MY_APP_REDIS_URL
```

```python
from l9_graphite_memory.runtime import build_runtime

runtime = build_runtime()
client = runtime.active_memory.client()  # ActiveAgentClient bound to Redis
```

`runtime.active_memory` is an `ActiveMemoryBinding`: it carries the backend,
the deployment identity, the `required` policy and the session parameters
(`L9_MEMORY_ACTIVE_HEARTBEAT_INTERVAL_SECONDS`, `L9_MEMORY_ACTIVE_LEASE_TTL_SECONDS`,
`L9_MEMORY_ACTIVE_HEARTBEAT_FAILURE_THRESHOLD`). A process that needs only
the binding builds it directly:

```python
from l9_graphite_memory.adapters import build_active_memory
from l9_graphite_memory.config import load_settings

binding = build_active_memory(load_settings())
client = binding.client()
```

The other credential sources are `L9_MEMORY_ACTIVE_REDIS_URL_FILE` (a mounted
file holding the URL), `L9_MEMORY_ACTIVE_REDIS_PASSWORD_FILE` with
`L9_MEMORY_ACTIVE_REDIS_HOST` / `_PORT` / `_DATABASE` / `_TLS` / `_USERNAME`,
and `L9_MEMORY_ACTIVE_REDIS_SECRET_REFERENCE` resolved by a `secret_provider`
callback passed to `build_runtime(secret_provider=...)` or
`build_active_memory(settings, secret_provider=...)`. That source is therefore
usable only by a consumer that composes the runtime itself; the `l9-memory`
CLI and `l9-memory-server` carry no provider callback and refuse it at startup
with the resolver's reason. Exactly one source must be set; the credential
never appears in settings, receipts or logs.

An async consumer releases the composed runtime with `await runtime.aclose()`
so the Redis connections are closed before it returns; `runtime.close()` is
the synchronous form.

With the default `L9_MEMORY_ACTIVE_BACKEND=none` the binding holds the null
adapters: every session operation raises `ActiveMemoryUnavailableError`, and
readiness reports the families as not selected.

## Proving the binding

```bash
l9-memory readiness        # exit 0 only when every required family is ready
curl -fsS http://127.0.0.1:8200/readyz
```

Both report the `active_store` and `awareness_bus` families on their own
probe (PING, scalar and sorted-set round trips; PING and PUBLISH), beside
`canonical`, `projection` and `graph`. An installed symbol is not proof; a
family that is required and absent or unhealthy makes the verdict `failed`.

## Using a session

```python
from l9_graphite_memory.active import AgentStatus

async with client.open_session(
    agent_id="research-agent",
    role="researcher",
    principal_id="authenticated-principal-id",
    group_ids=("project:example",),
) as agent:
    await agent.replace_context(
        objective="Review implementation",
        status=AgentStatus.ACTIVE,
        working_on=("contracts", "tests"),
    )

    peers = await agent.list_active(group_id="project:example")
    for peer in peers:
        shared = await agent.get_peer_context(peer.identity.agent_id, peer.identity.instance_id)

    async for event in agent.subscribe(group_id="project:example"):
        handle_event(event)
```

A session publishes lifecycle pointer events on the awareness bus by itself:
`agent.registered` on start, `agent.context.updated` after every
`replace_context`, `agent.draining` on `drain()` and `agent.unregistered` on
close. The bus is lossy by contract; a subscriber re-reads current state with
`list_active()` and `get_peer_context()` rather than trusting the stream to be
complete.

## What NOT to import

```python
# Do not do this from consumer application code:
from l9_graphite_memory.active.inmemory import InMemoryActiveStore  # internal reference adapter
from l9_graphite_memory.active.redis_adapters import RedisActiveStore  # internal Redis adapter
```

The in-memory adapter is a reference implementation used by this
package's own test suite. It is not covered by the SDK compatibility
policy below and may change without a major version bump.

## Compatibility policy

- **Patch** releases: internal fixes with no contract change.
- **Minor** releases: additive, backward-compatible fields or methods.
- **Major** releases: breaking lifecycle or contract changes.

`AgentEvent` and `ActiveContext` carry an explicit `schema_version`
field. Consumers must tolerate unknown additive fields and should
raise `SchemaCompatibilityError` (or an equivalent typed error) only
for unsupported major schema versions.

## Error handling

| Exception | Meaning | Recommended consumer action |
|---|---|---|
| `ActiveMemoryUnavailableError` | Backend unreachable or session not `ACTIVE` | Retry with backoff; do not block canonical memory operations |
| `ContextVersionConflictError` | Optimistic version check failed | Re-read current context, reapply change, retry |
| `LeaseExpiredError` | Lease no longer valid | Handled internally by the session; surfaces only if raised outside session lifecycle management |
| `SchemaCompatibilityError` | Unsupported major schema version observed | Upgrade consumer dependency on this package |
