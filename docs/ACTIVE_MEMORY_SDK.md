# Active Memory SDK Guide

This guide documents the only supported integration surface for the
active-memory subsystem: `ActiveAgentClient` and `ActiveAgentSession`,
exported from `l9graphitimemory.active`.

## Constructing a client

Consumer applications do not construct `ActiveAgentClient` directly in
this change (the runtime factory that wires it to a configured backend
is out of scope here — see MANIFEST.md "Unknowns/Deferred"). For
testing and for consumers wiring their own backend selection in the
interim, construct it directly against the in-memory reference adapter
or a future Redis adapter:

```python
from l9graphitimemory.active import ActiveAgentClient
from l9graphitimemory.active.inmemory import InMemoryActiveStore, InMemoryAwarenessBus
from l9graphitimemory.active.deployment import ActiveDeployment, DeploymentEnvironment
from datetime import datetime, timezone

deployment = ActiveDeployment(
    deployment_id="my-application-production",
    trust_domain="my-application",
    environment=DeploymentEnvironment.PRODUCTION,
)

store = InMemoryActiveStore(deployment, clock=lambda: datetime.now(timezone.utc))
bus = InMemoryAwarenessBus(deployment)

client = ActiveAgentClient(
    store=store,
    bus=bus,
    deployment_id=deployment.deployment_id,
)
```

## Using a session

```python
from l9graphitimemory.active import AgentStatus

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

    async for event in agent.subscribe(group_id="project:example"):
        handle_event(event)
```

## What NOT to import

```python
# Do not do this from consumer application code:
from l9graphitimemory.active.inmemory import InMemoryActiveStore  # internal reference adapter
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
