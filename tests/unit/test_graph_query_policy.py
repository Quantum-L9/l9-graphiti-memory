# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_query_policy.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Static Cypher template policy: no persistent mutation is expressible (ADR-085)."""

from __future__ import annotations

import ast
import inspect

import pytest

from l9_graphite_memory.adapters import neo4j_graph_intelligence as adapter_module
from l9_graphite_memory.adapters.neo4j_graph_intelligence import HEALTH_TEMPLATES
from l9_graphite_memory.adapters.neo4j_query_policy import (
    QueryRegistry,
    QueryTemplate,
    TemplateKind,
    audit_cypher_template,
)
from l9_graphite_memory.errors import GraphQueryPolicyViolation

FORBIDDEN_PORT_METHODS = {
    "execute_raw_cypher",
    "write_node",
    "write_edge",
    "merge_entity",
    "delete_entity",
    "mutate_persistent_graph",
    "gds_write",
    "execute_query",
    "run",
}


@pytest.mark.parametrize(
    "cypher",
    [
        "CREATE (n:Entity {uuid: $uuid})",
        "MERGE (n:Entity {uuid: $uuid}) RETURN n",
        "MATCH (n) SET n.name = $name",
        "MATCH (n) DELETE n",
        "MATCH (n) DETACH DELETE n",
        "MATCH (n) REMOVE n.name",
        "MATCH (n) FOREACH (x IN [1] | SET n.a = x)",
        "LOAD CSV FROM $url AS row RETURN row",
        "DROP INDEX entity_uuid",
        "DROP CONSTRAINT entity_key",
        "CALL { MATCH (n) RETURN n } IN TRANSACTIONS RETURN 1",
        "CALL gds.pageRank.write('g', {writeProperty: 'pr'})",
        "CALL gds.fastRP.mutate('g', {mutateProperty: 'e', embeddingDimension: 8})",
        "CALL gds.graph.export('g', {dbName: 'x'})",
        "CALL apoc.create.node(['X'], {})",
        "CALL dbms.setConfigValue('x', 'y')",
        "MATCH (n:{label}) RETURN n",
        "MATCH (n) WHERE n.name = %s RETURN n",
    ],
)
def test_mutation_or_composition_is_refused_at_registration(cypher: str) -> None:
    with pytest.raises(GraphQueryPolicyViolation):
        QueryTemplate("unsafe_probe_v1", TemplateKind.READ, cypher)


@pytest.mark.parametrize(
    "cypher",
    [
        "MATCH (n:Entity) WHERE n.created_at < $as_of RETURN n.uuid AS uuid SKIP $skip",
        "CALL dbms.components() YIELD name RETURN name",
        "MATCH (a)-[r]->(b) WHERE type(r) IN $relationship_types RETURN count(r) AS c",
    ],
)
def test_read_templates_with_mutation_like_substrings_are_accepted(cypher: str) -> None:
    audit_cypher_template("safe_probe_v1", cypher, TemplateKind.READ)


def test_gds_catalog_operation_requires_catalog_kind() -> None:
    with pytest.raises(GraphQueryPolicyViolation, match="catalog"):
        QueryTemplate("drop_probe_v1", TemplateKind.READ, "CALL gds.graph.drop($name, false)")
    QueryTemplate("drop_probe_v1", TemplateKind.GDS_CATALOG, "CALL gds.graph.drop($name, false)")


def test_registry_refuses_unregistered_duplicate_and_unversioned_templates() -> None:
    registry = QueryRegistry(HEALTH_TEMPLATES)
    with pytest.raises(GraphQueryPolicyViolation, match="unregistered"):
        registry.get("MATCH (n) RETURN n")
    with pytest.raises(GraphQueryPolicyViolation, match="duplicate"):
        QueryRegistry((HEALTH_TEMPLATES[0], HEALTH_TEMPLATES[0]))
    with pytest.raises(GraphQueryPolicyViolation, match="_vN"):
        QueryTemplate("probe", TemplateKind.READ, "RETURN 1 AS one")


def test_every_registered_template_passes_the_policy() -> None:
    for template in HEALTH_TEMPLATES:
        audit_cypher_template(template.name, template.cypher, template.kind)


def test_adapter_exposes_no_mutation_or_raw_query_surface() -> None:
    from l9_graphite_memory.adapters.neo4j_graph_intelligence import Neo4jGraphIntelligence

    public = {name for name in dir(Neo4jGraphIntelligence) if not name.startswith("_")}
    assert not public & FORBIDDEN_PORT_METHODS


def test_adapter_source_opens_only_read_transactions() -> None:
    source = inspect.getsource(adapter_module)
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert "execute_write" not in attributes
    assert "execute_query" not in attributes
    assert "write_transaction" not in attributes
    # The only statement execution is tx.run over a registered template.
    runs = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "run"
    ]
    assert len(runs) == 1
    first_arg = runs[0].args[0]
    assert isinstance(first_arg, ast.Attribute) and first_arg.attr == "cypher"
