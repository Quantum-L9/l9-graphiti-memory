# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/neo4j_graph_fixture.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Graphiti-shaped Neo4j fixture for live graph-intelligence tests.

Writes the constructs Graphiti v0.30.2 persists — ``Entity`` nodes,
``RELATES_TO`` edges carrying ``group_id``/``fact``/``episodes``/validity, and
``Episodic``-[:MENTIONS]->``Entity`` provenance — into unique GraphScopeKey
groups, through the test's own write session. The adapter under test never
writes; this fixture is the only writer, standing in for Graphiti.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from l9_graphite_memory.graph import graph_group_id

NEO4J_URI_ENV = "L9_MEMORY_TEST_NEO4J_URI"


def live_neo4j_settings() -> dict[str, str]:
    uri = os.environ.get(NEO4J_URI_ENV, "").strip()
    if not uri:
        pytest.skip(f"{NEO4J_URI_ENV} is not set; live graph-intelligence tests need Neo4j")
    return {
        "uri": uri,
        "database": os.environ.get("L9_MEMORY_TEST_NEO4J_DATABASE", "neo4j"),
        "user": os.environ.get("L9_MEMORY_TEST_NEO4J_USER", "neo4j"),
        "password": os.environ.get("L9_MEMORY_TEST_NEO4J_PASSWORD", ""),
    }


@dataclass
class GraphitiShapedGraph:
    settings: dict[str, str]
    suffix: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    groups: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        import neo4j

        self._driver = neo4j.GraphDatabase.driver(
            self.settings["uri"],
            auth=(self.settings["user"], self.settings["password"]),
            notifications_min_severity="OFF",
        )

    def group(self, tenant: str, namespace: str) -> str:
        group = graph_group_id(tenant, f"{namespace}-{self.suffix}")
        if group not in self.groups:
            self.groups.append(group)
        return group

    def namespace(self, namespace: str) -> str:
        return f"{namespace}-{self.suffix}"

    def _write(self, cypher: str, **parameters) -> None:
        with self._driver.session(database=self.settings["database"]) as session:
            session.execute_write(lambda tx: tx.run(cypher, parameters).consume())

    def entity(self, group: str, name: str, *, episodes: tuple[uuid.UUID, ...] = ()) -> uuid.UUID:
        entity_uuid = uuid.uuid4()
        self._write(
            "CREATE (n:Entity {uuid: $uuid, group_id: $group, name: $name, summary: $name})",
            uuid=str(entity_uuid),
            group=group,
            name=name,
        )
        for episode in episodes:
            self._write(
                "MERGE (ep:Episodic {uuid: $ep}) ON CREATE SET ep.group_id = $group, ep.content = 'x' "
                "WITH ep MATCH (n:Entity {uuid: $uuid}) "
                "CREATE (ep)-[:MENTIONS {uuid: randomUUID(), group_id: $group}]->(n)",
                ep=str(episode),
                group=group,
                uuid=str(entity_uuid),
            )
        return entity_uuid

    def relate(
        self,
        source: uuid.UUID,
        target: uuid.UUID,
        group: str,
        *,
        fact: str = "related",
        episodes: tuple[uuid.UUID, ...] = (),
        valid_at: datetime | None = None,
        invalid_at: datetime | None = None,
        expired_at: datetime | None = None,
    ) -> uuid.UUID:
        edge_uuid = uuid.uuid4()
        self._write(
            "MATCH (a:Entity {uuid: $source}), (b:Entity {uuid: $target}) "
            "CREATE (a)-[:RELATES_TO {uuid: $uuid, group_id: $group, name: 'RELATED', fact: $fact, "
            "episodes: $episodes, created_at: $created, valid_at: $valid_at, "
            "invalid_at: $invalid_at, expired_at: $expired_at}]->(b)",
            source=str(source),
            target=str(target),
            uuid=str(edge_uuid),
            group=group,
            fact=fact,
            episodes=[str(e) for e in episodes],
            created=datetime.now(timezone.utc) - timedelta(days=30),
            valid_at=valid_at,
            invalid_at=invalid_at,
            expired_at=expired_at,
        )
        return edge_uuid

    def ensure_fulltext_index(self) -> None:
        self._write(
            "CREATE FULLTEXT INDEX node_name_and_summary IF NOT EXISTS "
            "FOR (n:Entity) ON EACH [n.name, n.summary]"
        )
        with self._driver.session(database=self.settings["database"]) as session:
            session.run("CALL db.awaitIndexes(30)").consume()

    def cleanup(self) -> None:
        if self.groups:
            self._write("MATCH (n) WHERE n.group_id IN $groups DETACH DELETE n", groups=self.groups)
        self._driver.close()
