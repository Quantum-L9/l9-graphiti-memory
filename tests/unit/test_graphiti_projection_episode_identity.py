# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graphiti_projection_episode_identity.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Graphiti episode identity: provider-issued uuids, name locators (ADR-090)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from l9_graphite_memory.adapters import GraphitiProjection
from l9_graphite_memory.adapters.graphiti_projection import (
    episode_name,
    episode_name_locator,
    parse_episode_name_locator,
)
from l9_graphite_memory.errors import ProjectionError
from l9_graphite_memory.graph import graph_group_id
from tests.graph_fakes import seeded_memory

TOOLS = ["add_memory", "get_episodes", "delete_episode", "search_memory_facts", "search_nodes"]


class ScriptedTransport:
    name = "scripted-graphiti"

    def __init__(self, *, tools: list[str] | None = None, episodes=None, write_result=None):
        self.tools = TOOLS if tools is None else tools
        self.episodes: list[dict[str, Any]] = list(episodes or [])
        self.write_result = write_result or {"message": "Episode queued"}
        self.writes: list[dict[str, Any]] = []
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.facts: list[dict[str, Any]] = []

    def health(self) -> dict[str, Any]:
        return {"healthy": True}

    def list_tools(self) -> list[str]:
        return list(self.tools)

    def write(self, body: str, group_id: str, kind: str = "observation", **kwargs: Any) -> Any:
        self.writes.append({"group_id": group_id, **kwargs})
        return self.write_result

    def search(self, query: str, group_id: str, limit: int = 10) -> list[dict[str, Any]]:
        return []

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        arguments = arguments or {}
        self.calls.append((name, arguments))
        if name == "get_episodes":
            groups = set(arguments["group_ids"])
            return {"episodes": [e for e in self.episodes if e["group_id"] in groups]}
        if name == "delete_episode":
            return {"message": "deleted"}
        if name == "search_memory_facts":
            return {"facts": self.facts}
        raise KeyError(name)


def _record():
    _service, store, _principal, write = seeded_memory()
    return store.get_record(write("tenant-a", "falcon migration plan"))


def test_projection_names_the_episode_and_never_supplies_a_uuid() -> None:
    record = _record()
    transport = ScriptedTransport()
    result = GraphitiProjection(transport).project(record)
    group = graph_group_id(record.tenant_id, record.namespace)
    (write,) = transport.writes
    assert "uuid" not in write
    assert write["name"] == episode_name(record.record_id)
    assert write["group_id"] == group
    assert result["locator"] == episode_name_locator(group, record.record_id)
    assert parse_episode_name_locator(result["locator"]) == (group, write["name"])


def test_a_provider_issued_episode_uuid_is_the_locator() -> None:
    record = _record()
    transport = ScriptedTransport(write_result={"episode_uuid": "provider-7"})
    assert GraphitiProjection(transport).project(record)["locator"] == "provider-7"


def test_name_locator_resolves_in_its_own_group_and_deletes_every_match() -> None:
    record_id = uuid4()
    group = graph_group_id("tenant-a", "repo-a")
    other = graph_group_id("tenant-b", "repo-a")
    name = episode_name(record_id)
    transport = ScriptedTransport(
        episodes=[
            {"uuid": "ep-1", "name": name, "group_id": group},
            {"uuid": "ep-2", "name": name, "group_id": group},
            {"uuid": "ep-x", "name": name, "group_id": other},
            {"uuid": "ep-3", "name": episode_name(uuid4()), "group_id": group},
        ]
    )
    projection = GraphitiProjection(transport, episode_lookup_limit=25)
    result = projection.erase(record_id, "repo-a", locator=episode_name_locator(group, record_id))
    assert result["erased"] is True
    assert result["provider_result"]["deleted_episode_uuids"] == ["ep-1", "ep-2"]
    lookup = next(args for tool, args in transport.calls if tool == "get_episodes")
    assert lookup == {"group_ids": [group], "max_episodes": 25}
    deleted = [args["uuid"] for tool, args in transport.calls if tool == "delete_episode"]
    assert deleted == ["ep-1", "ep-2"]


@pytest.mark.parametrize("operation", ["retire", "erase"])
def test_an_unresolved_name_fails_closed(operation) -> None:
    record_id = uuid4()
    group = graph_group_id("tenant-a", "repo-a")
    transport = ScriptedTransport(episodes=[])
    projection = GraphitiProjection(transport)
    with pytest.raises(ProjectionError, match="not found in its graph scope"):
        getattr(projection, operation)(
            record_id, "repo-a", locator=episode_name_locator(group, record_id)
        )
    assert not [tool for tool, _ in transport.calls if tool == "delete_episode"]


def test_a_name_locator_needs_get_episodes() -> None:
    record_id = uuid4()
    group = graph_group_id("tenant-a", "repo-a")
    transport = ScriptedTransport(tools=["add_memory", "delete_episode"])
    with pytest.raises(ProjectionError, match="does not expose get_episodes"):
        GraphitiProjection(transport).retire(
            record_id, "repo-a", locator=episode_name_locator(group, record_id)
        )


def test_legacy_uuid_locators_delete_directly() -> None:
    transport = ScriptedTransport()
    record_id = uuid4()
    result = GraphitiProjection(transport).retire(record_id, "repo-a", locator=str(record_id))
    assert transport.calls == [("delete_episode", {"uuid": str(record_id)})]
    assert result["provider_result"] == {"message": "deleted"}


@pytest.mark.parametrize(
    "locator",
    [
        "graphiti-episode-name:",
        "graphiti-episode-name:l9g-v1-abc",
        "graphiti-episode-name:l9g-v1-abc:other:1",
        "l9g-v1-abc:memory:1",
    ],
)
def test_malformed_name_locators_are_not_name_locators(locator) -> None:
    assert parse_episode_name_locator(locator) is None


def test_lookup_limit_must_be_positive() -> None:
    with pytest.raises(ValueError):
        GraphitiProjection(ScriptedTransport(), episode_lookup_limit=0)


def test_fact_search_maps_provider_episodes_to_records_within_the_group() -> None:
    group = graph_group_id("tenant-a", "repo-a")
    other = graph_group_id("tenant-b", "repo-a")
    first, second, foreign = uuid4(), uuid4(), uuid4()
    transport = ScriptedTransport(
        episodes=[
            {"uuid": "ep-1", "name": episode_name(first), "group_id": group},
            {"uuid": "ep-2", "name": episode_name(second), "group_id": group},
            {"uuid": "ep-3", "name": "not-a-memory", "group_id": group},
            {"uuid": "ep-f", "name": episode_name(foreign), "group_id": other},
        ]
    )
    transport.facts = [
        {"fact": "Falcon relates to Payments", "episodes": ["ep-1", "ep-2", "ep-f"], "score": 0.8},
        {"fact": "orphan fact", "episodes": ["ep-3", "ep-missing"], "score": 0.9},
    ]
    hits = GraphitiProjection(transport).search_strategy(
        "semantic-search", "falcon", ("repo-a",), limit=10, tenant_id="tenant-a"
    )
    assert {hit.record_id for hit in hits} == {first, second}
    lookups = [args for tool, args in transport.calls if tool == "get_episodes"]
    assert lookups == [{"group_ids": [group], "max_episodes": 1000}]
