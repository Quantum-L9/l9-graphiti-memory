# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_zep_transport.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

from __future__ import annotations

from types import SimpleNamespace

import pytest

from l9_graphite_memory.errors import ProjectionError
from l9_graphite_memory.zep_transport import ZepCloudTransport


class FakeEpisodeApi:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete(self, *, uuid_: str):
        self.deleted.append(uuid_)
        return None


class FakeGraph:
    def __init__(self) -> None:
        self.fail = False
        self.episode = FakeEpisodeApi()

    def add(self, **_kwargs):
        if self.fail:
            raise RuntimeError("zep unavailable")
        return SimpleNamespace(uuid="episode-1")

    def search(self, **_kwargs):
        if self.fail:
            raise RuntimeError("zep unavailable")
        return SimpleNamespace(edges=[])


class FakeClient:
    def __init__(self) -> None:
        self.graph = FakeGraph()


def test_zep_health_is_unverified_until_real_operation() -> None:
    transport = ZepCloudTransport(api_key="", client=FakeClient())
    health = transport.health()
    assert health["configured"] is True
    assert health["connectivity_verified"] is False
    assert health["healthy"] is False
    assert health["status"] == "unverified"


def test_zep_health_becomes_healthy_after_successful_operation() -> None:
    transport = ZepCloudTransport(api_key="", client=FakeClient())
    transport.write("fact", "repo-a")
    health = transport.health()
    assert health["connectivity_verified"] is True
    assert health["healthy"] is True
    assert health["status"] == "healthy"


def test_zep_health_records_operation_failure() -> None:
    client = FakeClient()
    transport = ZepCloudTransport(api_key="", client=client)
    client.graph.fail = True
    with pytest.raises(ProjectionError, match="Zep graph search failed"):
        transport.search("query", "repo-a")
    health = transport.health()
    assert health["connectivity_verified"] is True
    assert health["healthy"] is False
    assert health["status"] == "unhealthy"
    assert health["error"] == "zep unavailable"


def test_zep_delete_uses_stable_episode_locator() -> None:
    client = FakeClient()
    transport = ZepCloudTransport(api_key="", client=client)
    result = transport.call_tool("delete_episode", {"uuid": "episode-1"})
    assert result["erased"] is True
    assert client.graph.episode.deleted == ["episode-1"]
