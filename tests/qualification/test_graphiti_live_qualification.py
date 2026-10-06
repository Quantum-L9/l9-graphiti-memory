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
``add_episode`` (real LLM extraction, embeddings and reranking; persistence
and indices) → the read-only graph-intelligence adapter → canonical evidence
binding → lifecycle withdrawal and verified erasure through
``remove_episode``; plus Graphiti process-restart recovery and ``graph.search``
entity binding (ADR-093).

Real extraction is not deterministic, so every assertion is a property:
scoping, provenance, canonical support and lifecycle — never an exact graph.
See ``docs/graph-intelligence/QUALIFICATION.md``. Skips unless
``graphiti_core`` is importable and ``L9_MEMORY_TEST_NEO4J_URI`` names a Neo4j
with GDS; fails, never falls back, when ``OPENAI_API_KEY`` is not bound.
"""

from __future__ import annotations

import os
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
from tests.qualification.graphiti_harness import GraphitiCoreTransport, model_stack

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

    def entity(self, tenant: str, token: str) -> UUID:
        """The extracted entity whose name best matches ``token`` in a tenant's group."""

        rows = self.rows(
            "MATCH (n:Entity) WHERE n.group_id = $group AND toLower(n.name) CONTAINS $token "
            "RETURN n.uuid AS uuid, n.name AS name ORDER BY size(n.name), n.name LIMIT 1",
            token=token.lower(),
            group=graph_group_id(tenant, self.ns),
        )
        assert rows, f"no extracted entity mentions {token!r} for {tenant}"
        return UUID(rows[0]["uuid"])

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


def _has(names, token: str) -> bool:
    """Whether an extracted name mentions ``token`` (LLM naming varies)."""

    return any(token in str(name).lower() for name in names)


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    world = World(tmp_path_factory.mktemp("qualification"))
    world.records = {
        "a1": world.write(
            "tenant-a",
            "Falcon is the payment routing service. Falcon depends on Payments. "
            "Payments writes every transaction to Ledger.",
        ),
        "a2": world.write(
            "tenant-a",
            "Osprey is the fraud screening service. Osprey calls Payments. "
            "Falcon forwards fraud alerts to Osprey.",
        ),
        "b1": world.write(
            "tenant-b", "Falcon is the nightly backup job. Falcon stores its archives in Vault."
        ),
    }
    world.stack = model_stack()
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
    """The upstream behavior ADR-091 routes around, observed on real Graphiti."""

    name = f"memory:{uuid4()}"
    reply = world.transport.write(
        '{"content": "probe"}', world.groups[0], name=name, uuid=str(uuid4())
    )
    assert "queued" in reply["message"]
    assert (name, "NodeNotFoundError") in world.transport.dropped
    assert not [row for row in world.episodes() if row["name"] == name]


def test_graphiti_extraction_builds_scoped_entities_and_edges(world) -> None:
    a, b = world.groups
    entities = world.rows(
        "MATCH (n:Entity) WHERE n.group_id IN $groups RETURN n.name AS name, n.group_id AS g",
        groups=world.groups,
    )
    a_names = {e["name"] for e in entities if e["g"] == a}
    b_names = {e["name"] for e in entities if e["g"] == b}
    for token in ("falcon", "payments", "ledger"):
        assert _has(a_names, token), token
    assert _has(b_names, "vault")
    # Tenant B's text never leaks into tenant A's graph, nor the reverse.
    assert not _has(a_names, "vault")
    assert not _has(b_names, "ledger")
    assert not _has(b_names, "osprey")
    edges = world.rows(
        "MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity) WHERE r.group_id IN $groups "
        "RETURN r.group_id AS g, s.group_id AS sg, t.group_id AS tg",
        groups=world.groups,
    )
    assert any(e["g"] == a for e in edges)
    assert any(e["g"] == b for e in edges)
    # Graphiti's own persistence keeps every edge inside one GraphScopeKey group.
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
    assert _has(names, "falcon")
    assert _has(names, "payments")
    assert not _has(names, "vault")
    support = set(receipt.supporting_record_ids)
    assert world.records["a1"] in support
    assert support <= {world.records["a1"], world.records["a2"]}


def test_another_tenant_cannot_reach_the_graph_through_a_shared_namespace(world) -> None:
    receipt = world.graph.execute(
        world.principal("tenant-b"),
        world.request(
            GraphOperation.NEIGHBORHOOD, anchor=GraphAnchor(record_id=world.records["a1"])
        ),
    )
    names = _node_names(receipt)
    for token in ("payments", "ledger", "osprey"):
        assert not _has(names, token), token
    assert world.records["a1"] not in receipt.supporting_record_ids
    falcon_b = world.graph.execute(
        world.principal("tenant-b"),
        world.request(
            GraphOperation.NEIGHBORHOOD,
            anchor=GraphAnchor(entity_uuid=world.entity("tenant-b", "falcon")),
        ),
    )
    assert falcon_b.status is GraphReceiptStatus.COMPLETE
    b_names = _node_names(falcon_b)
    assert _has(b_names, "vault")
    assert not _has(b_names, "payments")
    assert not _has(b_names, "ledger")
    assert set(falcon_b.supporting_record_ids) == {world.records["b1"]}


def test_path_and_neighborhood_over_the_real_graph(world) -> None:
    principal = world.principal("tenant-a")
    falcon, ledger = world.entity("tenant-a", "falcon"), world.entity("tenant-a", "ledger")
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
    assert paths
    assert 1 <= min(item["length"] for item in paths) <= 3
    neighborhood = world.graph.execute(
        principal,
        world.request(
            GraphOperation.NEIGHBORHOOD,
            anchor=GraphAnchor(entity_uuid=falcon),
            limits={"max_depth": 1},
        ),
    )
    assert neighborhood.status is GraphReceiptStatus.COMPLETE, neighborhood.failures
    assert _has(_node_names(neighborhood), "payments")


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
        "semantic-search", "Falcon Vault archives", (world.ns,), limit=10, tenant_id="tenant-b"
    )
    assert world.records["b1"] in {hit.record_id for hit in hits}
    assert {hit.record_id for hit in hits} <= {world.records["b1"]}


def test_entity_node_search_binds_canonical_support_on_real_graphiti(world) -> None:
    """ADR-093: Graphiti entity hits bind through MENTIONS -> episode -> record."""

    receipt = world.graph.execute(
        world.principal("tenant-a"),
        world.request(GraphOperation.SEARCH, anchor=GraphAnchor(query="Falcon")),
    )
    assert receipt.status is GraphReceiptStatus.COMPLETE, receipt.failures
    entity_hits = [item for item in receipt.results if item["kind"] == "entity_hit"]
    assert entity_hits
    assert _has({item["name"] for item in entity_hits}, "falcon")
    support = set(receipt.supporting_record_ids)
    assert support
    assert support <= {world.records["a1"], world.records["a2"]}
    assert str(world.records["b1"]) not in receipt.model_dump_json()


def test_supersession_and_verified_erasure_remove_real_episodes(world) -> None:
    principal = world.principal("tenant-a")
    old = world.write(
        "tenant-a",
        "Kestrel is owned by the Billing team.",
        assertion=MemoryAssertion(subject="kestrel", predicate="owner", object="billing"),
    )
    assert world.drain()["dead"] == 0
    assert episode_name(old) in {row["name"] for row in world.episodes()}
    new = world.write(
        "tenant-a",
        "Kestrel is owned by the Platform team.",
        assertion=MemoryAssertion(subject="kestrel", predicate="owner", object="platform"),
        supersedes=(old,),
    )
    assert world.drain()["dead"] == 0
    names = {row["name"] for row in world.episodes()}
    assert episode_name(old) not in names and episode_name(new) in names
    assert world.store.get_record(old).state is MemoryState.SUPERSEDED

    (new_episode,) = [row for row in world.episodes() if row["name"] == episode_name(new)]
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
    # Graphiti's remove_episode leaves no edge citing the erased episode.
    assert not world.rows(
        "MATCH ()-[r:RELATES_TO]->() WHERE r.group_id = $group AND $episode IN r.episodes "
        "RETURN r.uuid AS uuid",
        group=graph_group_id("tenant-a", world.ns),
        episode=new_episode["uuid"],
    )
    del principal


def test_graphiti_process_restart_recovers_and_keeps_the_projection(world) -> None:
    """GI-080 restart: a new Graphiti process binds the same graph and keeps projecting."""

    before = {row["name"] for row in world.episodes()}
    restarted = GraphitiCoreTransport(
        world.settings["uri"], world.settings["user"], world.settings["password"]
    )
    try:
        projection = GraphitiProjection(restarted)
        memory = MemoryService(world.store, projection)
        memory.initialize()
        worker = OutboxWorker(world.store, projection, MemorySettings(), worker_id="restarted")
        receipt = memory.write(
            world.principal("tenant-a"),
            MemoryWriteRequest(
                namespace=world.ns,
                content="Heron is the settlement service. Heron reads from Ledger.",
                provenance=Provenance(source="qualification-restart"),
            ),
        )
        for _ in range(10):
            if worker.run_once()["claimed"] == 0:
                break
        after = {row["name"] for row in world.episodes()}
        assert before <= after
        assert episode_name(receipt.record_id) in after
        assert restarted.dropped == []
        hits = projection.search_strategy(
            "semantic-search",
            "Heron settlement Ledger",
            (world.ns,),
            limit=10,
            tenant_id="tenant-a",
        )
        assert receipt.record_id in {hit.record_id for hit in hits}
    finally:
        restarted.close()


def test_the_qualified_model_stack_is_the_harvested_one(world) -> None:
    """Receipt of what ran: the settled stack, with the manifest's embedder."""

    assert world.stack["embedder"].endswith("text-embedding-3-large")
    assert world.stack["embedding_dim"] == 3072
    assert world.stack["llm"].endswith(("gpt-5.5", os.environ.get("MODEL_NAME") or "gpt-5.5"))
    assert world.stack["route"] in ("openai", "openrouter")
