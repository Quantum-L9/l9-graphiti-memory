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


def test_health_answers_while_the_tool_pool_is_saturated() -> None:
    import threading

    from l9_graphite_memory.server import await_health

    release = threading.Event()

    def stuck_tool() -> None:
        release.wait(5)

    async def scenario() -> str:
        stuck = [
            asyncio.ensure_future(await_blocking(stuck_tool)) for _ in range(HTTP_TOOL_WORKERS)
        ]
        try:
            await asyncio.sleep(0.05)  # every tool worker is now occupied
            return await asyncio.wait_for(await_health(lambda: "ok"), timeout=1.0)
        finally:
            release.set()
            await asyncio.gather(*stuck)

    assert asyncio.run(scenario()) == "ok"
