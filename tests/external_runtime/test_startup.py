"""External-runtime test: clean startup and registration."""

from __future__ import annotations

import pytest

from l9_graphite_memory.active.lifecycle import ActiveAgentSessionState
from l9_graphite_memory.active.models import AgentStatus


@pytest.mark.asyncio
async def test_session_starts_and_becomes_active(client) -> None:
    async with client.open_session(
        agent_id="agent-primary",
        role="personal_assistant",
        principal_id="principal-primary",
        group_ids=("project:test",),
    ) as session:
        assert session.state is ActiveAgentSessionState.ACTIVE
        assert session.background_exception() is None


@pytest.mark.asyncio
async def test_session_can_write_context_after_start(client) -> None:
    async with client.open_session(
        agent_id="agent-research",
        role="researcher",
        principal_id="principal-research",
    ) as session:
        context = await session.replace_context(
            objective="Review implementation",
            status=AgentStatus.ACTIVE,
            working_on=("contracts",),
        )
        assert context.version == 1
        assert context.draft.objective == "Review implementation"


@pytest.mark.asyncio
async def test_public_sdk_does_not_expose_redis_internals() -> None:
    import l9_graphite_memory.active as active_pkg

    exported = set(active_pkg.__all__)
    assert "RedisActiveStore" not in exported
    assert "RedisAwarenessBus" not in exported
