"""Adapter-conformance tests for the ActiveStore port.

Every ActiveStore implementation MUST pass these tests unmodified.
"""

from __future__ import annotations

import pytest

from l9_graphite_memory.active.errors import (
    ActiveMemoryUnavailableError,
    ContextVersionConflictError,
    LeaseExpiredError,
)
from l9_graphite_memory.active.models import (
    ActiveContextDraft,
    AgentIdentity,
    AgentLease,
    AgentScope,
    AgentStatus,
)
from tests.conformance.active.conftest import FakeClock


def _make_identity(
    agent_id: str = "agent-a", role: str = "researcher"
) -> AgentIdentity:
    return AgentIdentity(
        agent_id=agent_id,
        instance_id="instance-1",
        role=role,
        principal_id="principal-a",
        memory_group_ids=("project:conformance",),
    )


def _make_lease(clock: FakeClock, identity: AgentIdentity, ttl: int = 30) -> AgentLease:
    from datetime import timedelta

    now = clock()
    return AgentLease(
        lease_id="lease-1",
        agent_id=identity.agent_id,
        instance_id=identity.instance_id,
        issued_at=now,
        expires_at=now + timedelta(seconds=ttl),
        heartbeat_interval_seconds=10,
    )


@pytest.mark.asyncio
async def test_register_creates_presence(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    presence = await store.register(identity, lease)
    assert presence.identity.agent_id == "agent-a"
    assert presence.status == AgentStatus.STARTING


@pytest.mark.asyncio
async def test_renew_updates_heartbeat(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    await store.register(identity, lease)
    clock.advance(5)
    renewed = await store.renew(lease)
    assert renewed.heartbeat_at == clock()


@pytest.mark.asyncio
async def test_renew_expired_lease_raises(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity, ttl=10)
    await store.register(identity, lease)
    clock.advance(11)
    with pytest.raises(LeaseExpiredError):
        await store.renew(lease)


@pytest.mark.asyncio
async def test_unregister_is_idempotent(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    await store.register(identity, lease)
    await store.unregister(lease)
    await store.unregister(lease)


@pytest.mark.asyncio
async def test_put_context_first_write_requires_no_expected_version(
    store, clock
) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    await store.register(identity, lease)
    draft = ActiveContextDraft(objective="test objective", status=AgentStatus.ACTIVE)
    context = await store.put_context(lease, expected_version=None, draft=draft)
    assert context.version == 1


@pytest.mark.asyncio
async def test_put_context_version_conflict_raises(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    await store.register(identity, lease)
    draft = ActiveContextDraft(objective="v1", status=AgentStatus.ACTIVE)
    await store.put_context(lease, expected_version=None, draft=draft)
    with pytest.raises(ContextVersionConflictError):
        await store.put_context(lease, expected_version=0, draft=draft)


@pytest.mark.asyncio
async def test_put_context_correct_expected_version_succeeds(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    await store.register(identity, lease)
    draft_v1 = ActiveContextDraft(objective="v1", status=AgentStatus.ACTIVE)
    context_v1 = await store.put_context(lease, expected_version=None, draft=draft_v1)
    draft_v2 = ActiveContextDraft(objective="v2", status=AgentStatus.ACTIVE)
    context_v2 = await store.put_context(
        lease, expected_version=context_v1.version, draft=draft_v2
    )
    assert context_v2.version == context_v1.version + 1


@pytest.mark.asyncio
async def test_get_context_returns_none_after_expiry(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    await store.register(identity, lease)
    draft = ActiveContextDraft(objective="v1", status=AgentStatus.ACTIVE)
    await store.put_context(lease, expected_version=None, draft=draft)
    clock.advance(61)
    context = await store.get_context("agent-a", "instance-1")
    assert context is None


@pytest.mark.asyncio
async def test_get_presence_returns_none_after_expiry(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    await store.register(identity, lease)
    clock.advance(31)
    presence = await store.get_presence("agent-a", "instance-1")
    assert presence is None


@pytest.mark.asyncio
async def test_list_active_filters_by_role(store, clock) -> None:
    identity_a = _make_identity(agent_id="agent-a", role="researcher")
    identity_b = _make_identity(agent_id="agent-b", role="reviewer")
    await store.register(identity_a, _make_lease(clock, identity_a))
    await store.register(identity_b, _make_lease(clock, identity_b))

    scope = AgentScope(deployment_id="conformance-test", role="researcher")
    page = await store.list_active(scope, cursor=None, limit=10)
    agent_ids = {p.identity.agent_id for p in page.items}
    assert agent_ids == {"agent-a"}


@pytest.mark.asyncio
async def test_list_active_excludes_expired(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    await store.register(identity, lease)
    clock.advance(31)
    scope = AgentScope(deployment_id="conformance-test")
    page = await store.list_active(scope, cursor=None, limit=10)
    assert page.items == ()


@pytest.mark.asyncio
async def test_list_active_pagination(store, clock) -> None:
    for index in range(5):
        identity = AgentIdentity(
            agent_id=f"agent-{index}",
            instance_id=f"instance-{index}",
            role="researcher",
            principal_id="principal",
        )
        await store.register(identity, _make_lease(clock, identity))

    scope = AgentScope(deployment_id="conformance-test")
    first_page = await store.list_active(scope, cursor=None, limit=2)
    assert len(first_page.items) == 2
    assert first_page.next_cursor is not None

    second_page = await store.list_active(scope, cursor=first_page.next_cursor, limit=2)
    assert len(second_page.items) == 2

    first_ids = {p.identity.agent_id for p in first_page.items}
    second_ids = {p.identity.agent_id for p in second_page.items}
    assert first_ids.isdisjoint(second_ids)


@pytest.mark.asyncio
async def test_health_reports_healthy_by_default(store) -> None:
    health = await store.health()
    assert health.connectivity == "healthy"


@pytest.mark.asyncio
async def test_simulated_unavailability_raises_typed_error(store, clock) -> None:
    identity = _make_identity()
    lease = _make_lease(clock, identity)
    store.set_unavailable(True)
    with pytest.raises(ActiveMemoryUnavailableError):
        await store.register(identity, lease)
    store.set_unavailable(False)


@pytest.mark.asyncio
async def test_close_is_idempotent(store) -> None:
    await store.close()
    await store.close()
