# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_active_memory_redis_live.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.6.0
#   updated: 2026-07-22

"""Active memory over a real Redis, reached the way a consumer reaches it (ADR-097).

Two independently configured processes (two bindings built from settings,
two connections) share presence, context and awareness through one Redis
deployment; a third binding on another deployment identity sees nothing.
The outage case stops the real server with the commands the harness
supplies and proves the session degrades, canonical memory keeps working,
and recovery re-registers through the ADR-067 state machine once the lease
has lapsed.

The server is named by ``L9_MEMORY_TEST_REDIS_URL`` (CI: the job's Redis
service); without it every test here skips loudly.
"""

from __future__ import annotations

import asyncio
import os
import shlex
import subprocess
import time
import uuid

import pytest

from l9_graphite_memory.active import (
    ActiveAgentSessionState,
    ActiveMemoryBinding,
    AgentEvent,
    AgentEventType,
    AgentStatus,
)
from l9_graphite_memory.active.errors import ActiveMemoryUnavailableError
from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection, build_active_memory
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.services import MemoryService

REDIS_URL_ENV = "L9_MEMORY_TEST_REDIS_URL"
STOP_ENV = "L9_MEMORY_TEST_REDIS_STOP_CMD"
START_ENV = "L9_MEMORY_TEST_REDIS_START_CMD"
RECOVERY_TIMEOUT_S = 60.0


def _redis_url() -> str:
    url = os.environ.get(REDIS_URL_ENV, "").strip()
    if not url:
        pytest.skip(f"{REDIS_URL_ENV} is not set; live active-memory tests need Redis")
    return url


def _control(env: str) -> list[str]:
    command = os.environ.get(env, "").strip()
    if not command:
        pytest.skip(f"{env} is not set; the Redis outage case needs server control")
    return shlex.split(command)


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, timeout=60)


def _binding(
    prefix: str,
    *,
    deployment_id: str = "live-fleet",
    required: bool = True,
    lease_ttl: int = 30,
    heartbeat: int = 10,
) -> ActiveMemoryBinding:
    _redis_url()
    settings = MemorySettings(
        active_memory_backend="redis",
        active_memory_required=required,
        active_deployment_id=deployment_id,
        active_trust_domain="live",
        active_environment="test",
        active_redis_url_env=REDIS_URL_ENV,
        active_key_prefix=prefix,
        active_heartbeat_interval_seconds=heartbeat,
        active_lease_ttl_seconds=lease_ttl,
        active_heartbeat_failure_threshold=2,
    )
    return build_active_memory(settings)


@pytest.fixture
def prefix() -> str:
    return f"l9gm:live:{uuid.uuid4().hex}"


async def _purge(prefix: str) -> None:
    import redis.asyncio as redis

    client = redis.from_url(_redis_url(), decode_responses=True)
    try:
        async for key in client.scan_iter(match=f"{prefix}*"):
            await client.unlink(key)
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_two_independent_consumers_share_state_through_redis(prefix) -> None:
    a_binding, b_binding = _binding(prefix), _binding(prefix)
    stranger = _binding(prefix, deployment_id="other-fleet")
    received: list[AgentEvent] = []
    try:
        for binding in (a_binding, b_binding):
            health = await binding.health()
            assert health.healthy, health.error
            assert health.store["capabilities"] == ["ping", "scalar", "sorted_set"]
            assert health.bus["capabilities"] == ["ping", "publish"]

        a_client, b_client = a_binding.client(), b_binding.client()
        async with b_client.open_session(
            agent_id="observer", role="r", principal_id="p", group_ids=("team",)
        ) as observer:

            async def consume() -> None:
                async for event in observer.subscribe(group_id="team"):
                    received.append(event)
                    if event.event_type is AgentEventType.AGENT_CONTEXT_UPDATED:
                        break

            task = asyncio.ensure_future(consume())
            await asyncio.sleep(0.05)
            async with a_client.open_session(
                agent_id="worker", role="r", principal_id="p", group_ids=("team",)
            ) as worker:
                context = await worker.replace_context(
                    objective="shared over redis", status=AgentStatus.ACTIVE
                )
                await asyncio.wait_for(task, timeout=5.0)
                peers = await observer.list_active(group_id="team")
                assert {p.identity.agent_id for p in peers} == {"observer", "worker"}
                seen = await observer.get_peer_context("worker", worker.instance_id)
                assert seen is not None and seen.version == context.version
                assert seen.draft.objective == "shared over redis"

                async with stranger.client().open_session(
                    agent_id="outsider", role="r", principal_id="p", group_ids=("team",)
                ) as outsider:
                    others = await outsider.list_active(group_id="team")
                    assert {p.identity.agent_id for p in others} == {"outsider"}
                    assert await outsider.get_peer_context("worker", worker.instance_id) is None
            # The worker's teardown is visible too: its presence is gone.
            assert {p.identity.agent_id for p in await observer.list_active()} == {"observer"}
        kinds = [event.event_type for event in received]
        assert kinds[0] is AgentEventType.AGENT_REGISTERED
        assert kinds[-1] is AgentEventType.AGENT_CONTEXT_UPDATED
        assert all(event.agent_id == "worker" for event in received)
    finally:
        for binding in (a_binding, b_binding, stranger):
            await binding.close()
        await _purge(prefix)


@pytest.mark.asyncio
async def test_an_unreachable_backend_is_reported_not_assumed(prefix, monkeypatch) -> None:
    monkeypatch.setenv("L9_TEST_UNREACHABLE_REDIS", "redis://127.0.0.1:1/0")
    binding = build_active_memory(
        MemorySettings(
            active_memory_backend="redis",
            active_memory_required=True,
            active_deployment_id="live-fleet",
            active_trust_domain="live",
            active_redis_url_env="L9_TEST_UNREACHABLE_REDIS",
            active_key_prefix=prefix,
        )
    )
    try:
        health = await binding.health()
        assert health.healthy is False
        assert health.store["connectivity"] == "unavailable" and health.store["error"]
        assert health.bus["connectivity"] == "unavailable" and health.bus["error"]
        with pytest.raises(ActiveMemoryUnavailableError):
            async with binding.client().open_session(agent_id="a", role="r", principal_id="p"):
                pass
    finally:
        await binding.close()


def _wait_reachable(url: str) -> None:
    import redis

    deadline = time.monotonic() + RECOVERY_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with redis.from_url(url) as client:
                client.ping()
            return
        except redis.RedisError:
            time.sleep(0.5)
    raise AssertionError("Redis did not come back within the recovery timeout")


@pytest.mark.asyncio
async def test_a_real_outage_degrades_and_recovery_re_registers(prefix) -> None:
    stop, start = _control(STOP_ENV), _control(START_ENV)
    url = _redis_url()
    binding = _binding(prefix, lease_ttl=3, heartbeat=1)
    canonical = InMemoryRecordStore()
    memory = MemoryService(canonical, NullProjection())
    memory.initialize()
    principal = MemoryPrincipal(
        principal_id="p", tenant_id="t", read_namespaces=("ns",), write_namespaces=("ns",)
    )
    try:
        async with binding.client().open_session(
            agent_id="worker", role="r", principal_id="p"
        ) as session:
            first_instance = session.instance_id
            await asyncio.to_thread(_run, stop)
            try:
                await session._heartbeat_once()
                await session._heartbeat_once()
                assert session.state is ActiveAgentSessionState.DEGRADED
                down = await binding.health()
                assert down.healthy is False and down.store["connectivity"] == "unavailable"
                # Canonical memory is untouched by the active-memory outage.
                receipt = memory.write(
                    principal,
                    MemoryWriteRequest(
                        namespace="ns",
                        content="written during the redis outage",
                        provenance=Provenance(source="live"),
                    ),
                )
                hits = memory.search(
                    principal, MemorySearchRequest(namespaces=("ns",), query="outage")
                )
                assert {hit.record.record_id for hit in hits.hits} == {receipt.record_id}
                await asyncio.sleep(4)  # longer than the 3 s lease: recovery must re-register
            finally:
                await asyncio.to_thread(_run, start)
                await asyncio.to_thread(_wait_reachable, url)
            await session._heartbeat_once()
            assert session.state is ActiveAgentSessionState.ACTIVE
            assert session.instance_id != first_instance
            assert session.background_exception() is None
            await session.replace_context(objective="recovered", status=AgentStatus.ACTIVE)
            peers = await session.list_active()
            assert [p.identity.instance_id for p in peers] == [session.instance_id]
        up = await binding.health()
        assert up.healthy, up.error
    finally:
        await binding.close()
        _wait_reachable(url)
        await _purge(prefix)
