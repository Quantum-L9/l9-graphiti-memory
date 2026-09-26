# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/qualification/test_graphiti_live_qualification.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Live qualification against real Graphiti v0.30.2 on Neo4j 5.26 + GDS 2.13 (GI-080).

Canonical write → outbox → ``GraphitiProjection`` → ``graphiti_core``
``add_episode`` (real extraction pipeline, persistence and indices) → the
read-only graph-intelligence adapter → canonical evidence binding → lifecycle
withdrawal and verified erasure through ``remove_episode``.

The LLM, embedder and reranker are deterministic stand-ins
(``graphiti_harness``); see ``docs/graph-intelligence/QUALIFICATION.md`` for
exactly what this does and does not qualify. Skips unless ``graphiti_core`` is
importable and ``L9_MEMORY_TEST_NEO4J_URI`` names a Neo4j with GDS.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest

pytest.importorskip("graphiti_core", reason="qualification needs graphiti-core==0.30.2")
pytest.importorskip("neo4j", reason="qualification needs the neo4j driver")

import neo4j

from l9_graphite_memory.adapters import GraphitiProjection, SQLiteRecordStore
from l9_graphite_memory.adapters.graphiti_projection import (
    episode_name,
    episode_name_locator,
)
from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
)
from l9_graphite_memory.config import MemorySettings
from l9_graphite_memory.contracts import (
    DeletionRequest,
    DeletionStatus,
    MemoryAssertion,
    MemoryPrincipal,
    MemoryState,
    MemoryWriteRequest,
    Provenance,
)
from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphIntelligenceRequest,
    GraphOperation,
    GraphReceiptStatus,
)
from l9_graphite_memory.graph.service import GraphIntelligenceService
from l9_graphite_memory.services import MemoryService
from l9_graphite_memory.services.outbox_worker import OutboxWorker
from tests.integration.neo4j_graph_fixture import live_neo4j_settings
from tests.qualification.graphiti_harness import GraphitiCoreTransport

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


class World:
    def __init__(self, tmp: Path) -> None:
        self.settings = live_neo4j_settings()
        self.ns = f"qual-{uuid4().hex[:10]}"
        self.transport = GraphitiCoreTransport(
            self.settings["uri"], self.settings["user"], self.settings["password"]
        )
        self.store = SQLiteRecordStore(tmp / "qualification.sqlite3")
        self.projection = GraphitiProjection(self.transport)
        self.memory = MemoryService(self.store, self.projection)
        self.memory.initialize()
        self.worker = OutboxWorker(
            self.store, self.projection, MemorySettings(), worker_id="qualification"
        )
        self.adapter = Neo4jGraphIntelligence(Neo4jGraphIntelligenceConfig(**self.settings))
        self.graph = GraphIntelligenceService(
            self.store,
            self.adapter,
            namespace_policy=self.memory.namespace_policy,
            projection=self.projection,
        )
        self.driver = neo4j.GraphDatabase.driver(
            self.settings["uri"], auth=(self.settings["user"], self.settings["password"])
        )
        self.groups = [graph_group_id(t, self.ns) for t in ("tenant-a", "tenant-b")]

    def principal(self, tenant: str) -> MemoryPrincipal:
        return MemoryPrincipal(
            principal_id=f"{tenant}-agent",
            tenant_id=tenant,
            read_namespaces=(self.ns,),
            write_namespaces=(self.ns,),
            maintain_namespaces=(self.ns,),
        )

    def write(self, tenant: str, content: str, **kwargs: Any) -> UUID:
        receipt = self.memory.write(
            self.principal(tenant),
            MemoryWriteRequest(
                namespace=self.ns,
                content=content,
                provenance=Provenance(source="qualification"),
                **kwargs,
            ),
        )
        assert receipt.record_id is not None
        return receipt.record_id

    def drain(self) -> dict[str, int]:
        totals = {"delivered": 0, "retried": 0, "dead": 0}
        for _ in range(10):
            result = self.worker.run_once()
            for key in totals:
                totals[key] += result[key]
            if result["claimed"] == 0:
                break
        return totals

    def rows(self, cypher: str, **parameters: Any) -> list[dict[str, Any]]:
        records, _, _ = self.driver.execute_query(
            cypher, parameters, database_=self.settings["database"]
        )
        return [record.data() for record in records]

    def episodes(self) -> list[dict[str, Any]]:
        return self.rows(
            "MATCH (ep:Episodic) WHERE ep.group_id IN $groups "
            "RETURN ep.uuid AS uuid, ep.name AS name, ep.group_id AS group_id, "
            "ep.content AS content",
            groups=self.groups,
        )

    def entity(self, tenant: str, name: str) -> UUID:
        (row,) = self.rows(
            "MATCH (n:Entity {name: $name}) WHERE n.group_id = $group RETURN n.uuid AS uuid",
            name=name,
            group=graph_group_id(tenant, self.ns),
        )
        return UUID(row["uuid"])

    def request(self, operation: GraphOperation, **kwargs: Any) -> GraphIntelligenceRequest:
        return GraphIntelligenceRequest(operation=operation, namespaces=(self.ns,), **kwargs)

    def close(self) -> None:
        self.driver.execute_query(
            "MATCH (n) WHERE n.group_id IN $groups DETACH DELETE n",
            {"groups": self.groups},
            database_=self.settings["database"],
        )
        self.driver.close()
        self.adapter.close()
        self.transport.close()
        self.store.close()


def _node_names(receipt) -> set[str]:
    return {item["name"] for item in receipt.results if item.get("kind") == "node"}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    world = World(tmp_path_factory.mktemp("qualification"))
    world.records = {
        "a1": world.write("tenant-a", "falcon plan [[Falcon->Payments]] [[Payments->Ledger]]"),
        "a2": world.write("tenant-a", "osprey plan [[Osprey->Payments]] [[Falcon->Osprey]]"),
        "b1": world.write("tenant-b", "bravo plan [[Falcon->Vault]]"),
    }
    world.delivery = world.drain()
    yield world
    world.close()


def test_projection_ingests_named_episodes_with_provider_uuids(world) -> None:
    assert world.delivery["dead"] == 0 and world.delivery["delivered"] == 3
    assert world.transport.dropped == []
    episodes = {row["name"]: row for row in world.episodes()}
    for key, tenant in (("a1", "tenant-a"), ("a2", "tenant-a"), ("b1", "tenant-b")):
        record_id = world.records[key]
        row = episodes[episode_name(record_id)]
        assert row["group_id"] == graph_group_id(tenant, world.ns)
        assert row["uuid"] != str(record_id)
        link = world.store.get_projection_link(record_id, "graphiti")
        assert link is not None
        assert link.locator == episode_name_locator(row["group_id"], record_id)
    for row in episodes.values():
        assert "tenant-a" not in row["content"] and "tenant-b" not in row["content"]


def test_graphiti_rejects_a_caller_supplied_episode_uuid(world) -> None:
    """The upstream behavior ADR-090 routes around, observed on real Graphiti."""

    name = f"memory:{uuid4()}"
    reply = world.transport.write(
        '{"content": "probe"}', world.groups[0], name=name, uuid=str(uuid4())
    )
    assert "queued" in reply["message"]
    assert (name, "NodeNotFoundError") in world.transport.dropped
    assert not [row for row in world.episodes() if row["name"] == name]


def test_graphiti_extraction_builds_scoped_entities_and_edges(world) -> None:
    edges = world.rows(
        "MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity) WHERE r.group_id IN $groups "
        "RETURN s.name AS s, t.name AS t, r.group_id AS g, s.group_id AS sg, t.group_id AS tg",
        groups=world.groups,
    )
    a, b = world.groups
    assert {(e["s"], e["t"]) for e in edges if e["g"] == a} == {
        ("Falcon", "Payments"),
        ("Payments", "Ledger"),
        ("Osprey", "Payments"),
        ("Falcon", "Osprey"),
    }
    assert {(e["s"], e["t"]) for e in edges if e["g"] == b} == {("Falcon", "Vault")}
    assert all(e["g"] == e["sg"] == e["tg"] for e in edges)


def test_backend_health_qualifies_the_real_graphiti_schema(world) -> None:
    health = world.adapter.health()
    assert health.reachable and health.healthy
    assert health.schema_compatible
    assert health.missing_labels == () and health.missing_relationship_types == ()
    assert health.analytics_available and health.analytics_version
    assert health.scope_scheme_conformant is True
    assert health.schema_fingerprint


def test_record_anchor_resolves_through_the_episode_name_and_binds_support(world) -> None:
    receipt = world.graph.execute(
        world.principal("tenant-a"),
        world.request(
            GraphOperation.NEIGHBORHOOD, anchor=GraphAnchor(record_id=world.records["a1"])
        ),
    )
    assert receipt.status is GraphReceiptStatus.COMPLETE, receipt.failures
    names = _node_names(receipt)
    assert {"Falcon", "Payments", "Ledger", "Osprey"} <= names
    assert "Vault" not in names
    assert set(receipt.supporting_record_ids) == {world.records["a1"], world.records["a2"]}
    assert receipt.unsupported_projection_observations == ()


def test_another_tenant_cannot_reach_the_graph_through_a_shared_namespace(world) -> None:
    receipt = world.graph.execute(
        world.principal("tenant-b"),
        world.request(
            GraphOperation.NEIGHBORHOOD, anchor=GraphAnchor(record_id=world.records["a1"])
        ),
    )
    assert not _node_names(receipt) & {"Payments", "Ledger", "Osprey"}
    assert world.records["a1"] not in receipt.supporting_record_ids
    falcon_b = world.graph.execute(
        world.principal("tenant-b"),
        world.request(
            GraphOperation.NEIGHBORHOOD,
            anchor=GraphAnchor(entity_uuid=world.entity("tenant-b", "Falcon")),
        ),
    )
    assert falcon_b.status is GraphReceiptStatus.COMPLETE
    assert _node_names(falcon_b) == {"Falcon", "Vault"}
    assert set(falcon_b.supporting_record_ids) == {world.records["b1"]}


def test_path_and_traversal_over_the_real_graph(world) -> None:
    principal = world.principal("tenant-a")
    falcon, ledger = world.entity("tenant-a", "Falcon"), world.entity("tenant-a", "Ledger")
    path = world.graph.execute(
        principal,
        world.request(
            GraphOperation.PATH,
            anchor=GraphAnchor(entity_uuid=falcon),
            target=GraphAnchor(entity_uuid=ledger),
            limits={"max_depth": 3},
        ),
    )
    assert path.status is GraphReceiptStatus.COMPLETE, path.failures
    paths = [item for item in path.results if item.get("kind") == "path"]
    assert paths and min(item["length"] for item in paths) == 2
    traverse = world.graph.execute(
        principal,
        world.request(
            GraphOperation.TRAVERSE,
            anchor=GraphAnchor(entity_uuid=falcon),
            direction="out",
            limits={"max_depth": 1},
        ),
    )
    assert traverse.status is GraphReceiptStatus.COMPLETE, traverse.failures
    assert _node_names(traverse) == {
        "Falcon",
        "Payments",
        "Osprey",
    }


@pytest.mark.parametrize(
    ("operation", "algorithm"),
    [
        (GraphOperation.CENTRALITY, "pagerank"),
        (GraphOperation.COMMUNITY, "louvain"),
        (GraphOperation.STRUCTURAL_EMBEDDING, "fastrp"),
    ],
)
def test_gds_analytics_over_the_real_graph(world, operation, algorithm) -> None:
    receipt = world.graph.execute(
        world.principal("tenant-a"), world.request(operation, algorithm=algorithm)
    )
    assert receipt.status is GraphReceiptStatus.COMPLETE, receipt.failures
    assert receipt.results
    assert set(receipt.supporting_record_ids) <= {world.records["a1"], world.records["a2"]}
    assert receipt.supporting_record_ids
    leftover = world.rows("CALL gds.graph.list() YIELD graphName RETURN graphName")
    assert not [row for row in leftover if row["graphName"].startswith("l9gi_")]


def test_fact_search_maps_episodes_back_to_canonical_records(world) -> None:
    principal = world.principal("tenant-a")
    receipt = world.graph.execute(
        principal,
        world.request(GraphOperation.SEMANTIC_SEARCH, anchor=GraphAnchor(query="Falcon Payments")),
    )
    assert receipt.status is GraphReceiptStatus.COMPLETE, receipt.failures
    assert world.records["a1"] in receipt.supporting_record_ids
    assert world.records["b1"] not in receipt.supporting_record_ids
    hits = world.projection.search_strategy(
        "semantic-search", "Falcon Vault", (world.ns,), limit=10, tenant_id="tenant-b"
    )
    assert {hit.record_id for hit in hits} == {world.records["b1"]}


def test_entity_node_search_has_no_canonical_mapping_on_real_graphiti(world) -> None:
    """Known limitation (ADR-090): Graphiti entity nodes carry no episode ids.

    ``search_nodes`` returns entities with name and summary only, so
    ``graph.search`` answers COMPLETE with no canonical support rather than
    guessing. Structural operations reach the same entities with support.
    """

    receipt = world.graph.execute(
        world.principal("tenant-a"),
        world.request(GraphOperation.SEARCH, anchor=GraphAnchor(query="Falcon")),
    )
    assert receipt.status is GraphReceiptStatus.COMPLETE, receipt.failures
    assert receipt.supporting_record_ids == ()
    assert receipt.results == ()


def test_supersession_and_verified_erasure_remove_real_episodes(world) -> None:
    principal = world.principal("tenant-a")
    old = world.write(
        "tenant-a",
        "kestrel owner [[Kestrel->Billing]]",
        assertion=MemoryAssertion(subject="kestrel", predicate="owner", object="billing"),
    )
    assert world.drain()["dead"] == 0
    assert episode_name(old) in {row["name"] for row in world.episodes()}
    new = world.write(
        "tenant-a",
        "kestrel owner [[Kestrel->Platform]]",
        assertion=MemoryAssertion(subject="kestrel", predicate="owner", object="platform"),
        supersedes=(old,),
    )
    assert world.drain()["dead"] == 0
    names = {row["name"] for row in world.episodes()}
    assert episode_name(old) not in names and episode_name(new) in names
    assert world.store.get_record(old).state is MemoryState.SUPERSEDED

    admin = MemoryPrincipal(
        principal_id="admin",
        tenant_id="tenant-a",
        read_namespaces=("*",),
        write_namespaces=("*",),
        is_admin=True,
    )
    deletion = world.memory.delete(
        admin,
        DeletionRequest(record_id=new, reason="subject request", verification_reference="q-1"),
    )
    assert deletion.status is DeletionStatus.PENDING_PROJECTION
    assert world.drain()["dead"] == 0
    assert episode_name(new) not in {row["name"] for row in world.episodes()}
    assert world.store.get_record(new).state is MemoryState.DELETED
    # Graphiti's remove_episode drops edges only that episode supported.
    assert not world.rows(
        "MATCH (:Entity {name: 'Kestrel'})-[r:RELATES_TO]->(:Entity {name: 'Platform'}) "
        "WHERE r.group_id = $group RETURN r.uuid AS uuid",
        group=graph_group_id("tenant-a", world.ns),
    )
    del principal
