# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/security/test_graph_tenant_isolation.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Release-blocking: two tenants sharing a namespace never share a graph group.

ADR-084 / GI-009..GI-013. The fake provider below behaves like the official
Graphiti MCP server: episodes are stored under the ``group_id`` they were
written with, and searches only see the ``group_ids`` they name.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from l9_graphite_memory.adapters import GraphitiProjection, InMemoryRecordStore
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    MemoryPrincipal,
    MemorySearchRequest,
    MemoryWriteRequest,
    ProjectionLink,
    Provenance,
)
from l9_graphite_memory.graph import GRAPH_SCOPE_SCHEME, graph_group_id
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.outbox_worker import OutboxWorker

NAMESPACE = "shared"


class GroupedGraphitiTransport:
    """In-memory Graphiti: episodes partitioned by group id."""

    name = "grouped-graphiti"

    def __init__(self) -> None:
        self.episodes: dict[str, dict[str, Any]] = {}
        self.search_groups: list[tuple[str, ...]] = []
        self.injected_record_ids: list[UUID] = []

    def health(self) -> dict[str, Any]:
        return {"healthy": True}

    def list_tools(self) -> list[str]:
        return ["add_memory", "search_memory_facts", "search_nodes", "delete_episode"]

    def write(self, body: str, group_id: str, kind: str = "observation", **kwargs: Any) -> Any:
        # Graphiti would treat a supplied uuid as an update (ADR-090); the
        # projection names the episode instead. This provider keys episodes by
        # the record id in that name and issues it back as the episode uuid.
        assert "uuid" not in kwargs
        uuid = str(kwargs["name"]).removeprefix("memory:")
        self.episodes[uuid] = {"uuid": uuid, "group_id": group_id, "body": body}
        return {"uuid": uuid}

    def search(self, query: str, group_id: str, limit: int = 10) -> list[dict[str, Any]]:
        raise AssertionError("strategy search must be used")

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        arguments = arguments or {}
        if name == "delete_episode":
            self.episodes.pop(str(arguments["uuid"]), None)
            return {"message": "deleted"}
        groups = tuple(arguments.get("group_ids") or ())
        self.search_groups.append(groups)
        terms = {term.lower() for term in str(arguments.get("query", "")).split()}
        items = [
            {"record_id": episode["uuid"], "content": episode["body"], "score": 0.9}
            for episode in self.episodes.values()
            if episode["group_id"] in groups
            and any(term in episode["body"].lower() for term in terms)
        ]
        # A misbehaving provider can still name any record id; canonical
        # rehydration must refuse it.
        items.extend(
            {"record_id": str(record_id), "content": "injected", "score": 1.0}
            for record_id in self.injected_record_ids
        )
        key = "nodes" if name == "search_nodes" else "facts"
        return {key: items}


def _principal(tenant: str) -> MemoryPrincipal:
    return MemoryPrincipal(
        principal_id=f"{tenant}-agent",
        tenant_id=tenant,
        read_namespaces=(NAMESPACE,),
        write_namespaces=(NAMESPACE,),
        maintain_namespaces=(NAMESPACE,),
    )


@pytest.fixture
def stack() -> tuple[MemoryService, OutboxWorker, InMemoryRecordStore, GroupedGraphitiTransport]:
    store = InMemoryRecordStore()
    transport = GroupedGraphitiTransport()
    projection = GraphitiProjection(transport)
    service = MemoryService(store, projection)
    service.initialize()
    worker = OutboxWorker(store, projection, MemorySettings(), worker_id="scope-test")
    return service, worker, store, transport


def _write(service: MemoryService, tenant: str, content: str) -> UUID:
    receipt = service.write(
        _principal(tenant),
        MemoryWriteRequest(
            namespace=NAMESPACE,
            content=content,
            provenance=Provenance(source="scope-test"),
        ),
    )
    assert receipt.record_id is not None
    return receipt.record_id


def _drain(worker: OutboxWorker) -> None:
    for _ in range(5):
        if worker.run_once()["claimed"] == 0:
            return


def test_colliding_namespace_projects_into_distinct_tenant_groups(stack) -> None:
    service, worker, _store, transport = stack
    a_id = _write(service, "tenant-a", "alpha falcon migration plan")
    b_id = _write(service, "tenant-b", "bravo falcon migration plan")
    _drain(worker)

    assert transport.episodes[str(a_id)]["group_id"] == graph_group_id("tenant-a", NAMESPACE)
    assert transport.episodes[str(b_id)]["group_id"] == graph_group_id("tenant-b", NAMESPACE)
    assert transport.episodes[str(a_id)]["group_id"] != transport.episodes[str(b_id)]["group_id"]
    for episode in transport.episodes.values():
        assert "tenant-a" not in episode["body"]
        assert "tenant-b" not in episode["body"]
        assert GRAPH_SCOPE_SCHEME in episode["body"]


def test_each_tenant_searches_only_its_own_group(stack) -> None:
    service, worker, _store, transport = stack
    a_id = _write(service, "tenant-a", "alpha falcon migration plan")
    b_id = _write(service, "tenant-b", "bravo falcon migration plan")
    _drain(worker)

    for tenant, own, other in (("tenant-a", a_id, b_id), ("tenant-b", b_id, a_id)):
        transport.search_groups.clear()
        receipt = service.search(
            _principal(tenant),
            MemorySearchRequest(query="falcon migration", namespaces=(NAMESPACE,)),
        )
        returned = {result.record.record_id for result in receipt.hits}
        assert own in returned
        assert other not in returned
        assert transport.search_groups
        assert all(
            groups == (graph_group_id(tenant, NAMESPACE),) for groups in transport.search_groups
        )


def test_provider_naming_another_tenants_record_is_dropped(stack) -> None:
    service, worker, _store, transport = stack
    _write(service, "tenant-a", "alpha falcon migration plan")
    b_id = _write(service, "tenant-b", "bravo unrelated content")
    _drain(worker)
    transport.injected_record_ids.append(b_id)

    receipt = service.search(
        _principal("tenant-a"),
        MemorySearchRequest(query="falcon migration", namespaces=(NAMESPACE,)),
    )
    assert b_id not in {result.record.record_id for result in receipt.hits}


def test_request_cannot_supply_a_group_id() -> None:
    with pytest.raises(ValidationError):
        MemorySearchRequest(
            query="falcon",
            namespaces=(NAMESPACE,),
            group_ids=(graph_group_id("tenant-b", NAMESPACE),),  # type: ignore[call-arg]
        )


def test_rebuild_reprojects_records_linked_under_legacy_scheme(stack) -> None:
    service, worker, store, transport = stack
    a_id = _write(service, "tenant-a", "alpha falcon migration plan")
    _drain(worker)
    # Simulate a link written before ADR-084: namespace-keyed group, no scheme.
    legacy = store.get_projection_link(a_id, "graphiti")
    assert legacy is not None
    store.save_projection_link(
        ProjectionLink(
            record_id=a_id,
            namespace=NAMESPACE,
            projection_name="graphiti",
            locator=legacy.locator,
            metadata={"transport_result": {}},
        )
    )
    transport.episodes[str(a_id)]["group_id"] = NAMESPACE

    receipt = service.rebuild_projection(_principal("tenant-a"), NAMESPACE, apply=True)
    assert receipt.stale_scope_record_ids == (a_id,)
    assert a_id in receipt.queued_record_ids
    _drain(worker)

    relinked = store.get_projection_link(a_id, "graphiti")
    assert relinked is not None
    assert relinked.metadata["scope_scheme"] == GRAPH_SCOPE_SCHEME
    assert transport.episodes[str(a_id)]["group_id"] == graph_group_id("tenant-a", NAMESPACE)

    again = service.rebuild_projection(_principal("tenant-a"), NAMESPACE, apply=False)
    assert again.stale_scope_record_ids == ()
    assert again.queued_record_ids == ()
