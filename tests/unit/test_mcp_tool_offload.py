"""A blocking MCP tool call stays off the event loop."""

from __future__ import annotations

import asyncio
import time

from l9_graphite_memory.server import HTTP_TOOL_WORKERS, await_blocking


def test_the_tool_pool_is_bounded() -> None:
    assert HTTP_TOOL_WORKERS == 8


def test_a_blocking_call_does_not_stall_the_loop() -> None:
    order: list[str] = []

    def slow() -> str:
        time.sleep(0.3)
        order.append("tool")
        return "tool"

    async def run() -> None:
        task = asyncio.create_task(await_blocking(slow))
        await asyncio.sleep(0.05)
        order.append("health")
        assert await task == "tool"

    asyncio.run(run())
    assert order == ["health", "tool"]
