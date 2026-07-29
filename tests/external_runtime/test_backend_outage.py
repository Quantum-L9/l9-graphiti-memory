"""External-runtime tests: backend outage, degradation, and recovery."""

from __future__ import annotations

import pytest

from l9_graphite_memory.active.lifecycle import ActiveAgentSessionState


@pytest.mark.asyncio
async def test_outage_transitions_session_to_degraded(client, active_store) -> None:
    async with client.open_session(
        agent_id="agent-primary",
        role="personal_assistant",
        principal_id="principal-primary",
    ) as session:
        active_store.set_unavailable(True)
        # Two failed heartbeats exceed heartbeat_failure_threshold=2.
        await session._heartbeat_once()
        await session._heartbeat_once()
        assert session.state is ActiveAgentSessionState.DEGRADED
        active_store.set_unavailable(False)


@pytest.mark.asyncio
async def test_recovery_after_outage_returns_to_active(client, active_store) -> None:
    async with client.open_session(
        agent_id="agent-primary",
        role="personal_assistant",
        principal_id="principal-primary",
    ) as session:
        active_store.set_unavailable(True)
        await session._heartbeat_once()
        await session._heartbeat_once()
        assert session.state is ActiveAgentSessionState.DEGRADED

        active_store.set_unavailable(False)
        await session._heartbeat_once()
        assert session.state is ActiveAgentSessionState.ACTIVE


@pytest.mark.asyncio
async def test_writes_rejected_while_degraded(client, active_store) -> None:
    from l9_graphite_memory.active.errors import ActiveMemoryUnavailableError
    from l9_graphite_memory.active.models import AgentStatus

    async with client.open_session(
        agent_id="agent-primary",
        role="personal_assistant",
        principal_id="principal-primary",
    ) as session:
        active_store.set_unavailable(True)
        await session._heartbeat_once()
        await session._heartbeat_once()
        assert session.state is ActiveAgentSessionState.DEGRADED

        with pytest.raises(ActiveMemoryUnavailableError):
            await session.replace_context(
                objective="attempt", status=AgentStatus.ACTIVE
            )
        active_store.set_unavailable(False)
