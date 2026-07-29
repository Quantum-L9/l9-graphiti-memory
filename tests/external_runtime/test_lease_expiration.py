"""External-runtime tests: lease expiration and re-registration."""

from __future__ import annotations

import pytest

from l9_graphite_memory.active.lifecycle import ActiveAgentSessionState


@pytest.mark.asyncio
async def test_expired_lease_triggers_reregistration_with_new_instance_id(
    client, active_store, clock
) -> None:
    async with client.open_session(
        agent_id="agent-primary",
        role="personal_assistant",
        principal_id="principal-primary",
    ) as session:
        original_instance_id = session.instance_id
        clock.advance(4)  # exceeds lease_ttl_seconds=3
        await session._heartbeat_once()
        assert session.instance_id != original_instance_id
        assert session.state is ActiveAgentSessionState.ACTIVE


@pytest.mark.asyncio
async def test_reregistration_preserves_stable_agent_id(
    client, active_store, clock
) -> None:
    async with client.open_session(
        agent_id="agent-primary",
        role="personal_assistant",
        principal_id="principal-primary",
    ) as session:
        clock.advance(4)
        await session._heartbeat_once()
        presence = await active_store.get_presence("agent-primary", session.instance_id)
        assert presence is not None
        assert presence.identity.agent_id == "agent-primary"
