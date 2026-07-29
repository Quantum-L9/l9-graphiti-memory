"""Adapter-conformance tests for the AwarenessBus port.

Every AwarenessBus implementation MUST pass these tests unmodified.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from l9_graphite_memory.active.errors import ActiveMemoryUnavailableError
from l9_graphite_memory.active.models import (
    AgentEvent,
    AgentEventType,
    AgentScope,
    AgentSubscription,
)


def _make_event(
    *,
    event_id: str = "event-1",
    group_id: str | None = "project:conformance",
    role: str = "researcher",
) -> AgentEvent:
    return AgentEvent(
        event_id=event_id,
        event_type=AgentEventType.AGENT_CONTEXT_UPDATED,
        agent_id="agent-a",
        instance_id="instance-1",
        role=role,
        deployment_id="conformance-test",
        occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        group_id=group_id,
    )


@pytest.mark.asyncio
async def test_publish_with_no_subscribers_does_not_raise(bus) -> None:
    await bus.publish(_make_event())


@pytest.mark.asyncio
async def test_subscriber_receives_matching_event(bus) -> None:
    scope = AgentScope(deployment_id="conformance-test", group_id="project:conformance")
    subscription = AgentSubscription(scope=scope)
    received: list[AgentEvent] = []

    async def consume() -> None:
        async for event in bus.subscribe(subscription):
            received.append(event)
            break

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.01)
    await bus.publish(_make_event())
    await asyncio.wait_for(task, timeout=1.0)

    assert len(received) == 1
    assert received[0].event_id == "event-1"


@pytest.mark.asyncio
async def test_subscriber_does_not_receive_non_matching_group(bus) -> None:
    scope = AgentScope(deployment_id="conformance-test", group_id="project:other")
    subscription = AgentSubscription(scope=scope)
    received: list[AgentEvent] = []

    async def consume() -> None:
        async for event in bus.subscribe(subscription):
            received.append(event)

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.01)
    await bus.publish(_make_event(group_id="project:conformance"))
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert received == []


@pytest.mark.asyncio
async def test_deployment_isolation_is_enforced(bus) -> None:
    scope = AgentScope(deployment_id="other-deployment")
    subscription = AgentSubscription(scope=scope)
    received: list[AgentEvent] = []

    async def consume() -> None:
        async for event in bus.subscribe(subscription):
            received.append(event)

    task = asyncio.ensure_future(consume())
    await asyncio.sleep(0.01)
    await bus.publish(_make_event())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert received == []


@pytest.mark.asyncio
async def test_simulated_unavailability_raises_typed_error(bus) -> None:
    bus.set_unavailable(True)
    with pytest.raises(ActiveMemoryUnavailableError):
        await bus.publish(_make_event())
    bus.set_unavailable(False)


@pytest.mark.asyncio
async def test_close_is_idempotent(bus) -> None:
    await bus.close()
    await bus.close()
