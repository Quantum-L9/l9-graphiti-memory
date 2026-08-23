# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/external_runtime/test_graceful_shutdown.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""External-runtime tests: graceful shutdown, idempotent close, cleanup."""

from __future__ import annotations

import pytest

from l9_graphite_memory.active.lifecycle import ActiveAgentSessionState


@pytest.mark.asyncio
async def test_close_unregisters_lease(client, active_store) -> None:
    async with client.open_session(
        agent_id="agent-primary",
        role="personal_assistant",
        principal_id="principal-primary",
    ) as session:
        instance_id = session.instance_id

    presence = await active_store.get_presence("agent-primary", instance_id)
    assert presence is None


@pytest.mark.asyncio
async def test_close_is_idempotent(client) -> None:
    async with client.open_session(
        agent_id="agent-primary",
        role="personal_assistant",
        principal_id="principal-primary",
    ) as session:
        pass
    await session.close()
    await session.close()
    assert session.state is ActiveAgentSessionState.CLOSED


@pytest.mark.asyncio
async def test_client_close_releases_store_and_bus(client, active_store, awareness_bus) -> None:
    async with client.open_session(
        agent_id="agent-primary",
        role="personal_assistant",
        principal_id="principal-primary",
    ):
        pass
    await client.close()
