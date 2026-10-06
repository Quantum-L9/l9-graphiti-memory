# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/neo4j_gds_templates.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Static GDS 2.13 analytics templates, stream mode only (ADR-088).

Every analytic runs against an ephemeral, scope-bound in-memory graph that the
adapter projects from the authorized GraphScopeKey groups with a Cypher
aggregation, streams, and drops in ``finally``. No template writes, mutates,
or exports: the registration audit refuses ``.write``/``.mutate``/export, and
GDS catalog operations are confined to ``GDS_CATALOG`` templates. Graph names
are bound parameters, never interpolated.

Link prediction is computed in-scope in Cypher (common neighbours and their
in-scope degrees); ``gds.alpha.linkprediction.*`` would count neighbours
across the whole database, outside the authorized groups.
"""

from __future__ import annotations

from .neo4j_query_policy import QueryTemplate, TemplateKind

GRAPH_NAME_PREFIX = "l9gi_"
ORIENTATIONS = ("natural", "reverse", "undirected")

_REL_FILTER = (
    "s.group_id IN $group_ids AND t.group_id IN $group_ids AND r.group_id IN $group_ids "
    "AND type(r) IN $relationship_types "
    "AND ($as_of IS NULL OR ((r.valid_at IS NULL OR r.valid_at <= $as_of) "
    "AND (r.invalid_at IS NULL OR r.invalid_at > $as_of))) "
    "AND (CASE WHEN $recorded_before IS NULL THEN r.expired_at IS NULL "
    "ELSE ((r.created_at IS NULL OR r.created_at <= $recorded_before) "
    "AND (r.expired_at IS NULL OR r.expired_at > $recorded_before)) END)"
)
_SCOPED = f"MATCH (s:Entity)-[r:RELATES_TO]->(t:Entity) WHERE {_REL_FILTER} "
_PROJECT = {
    "natural": "WITH gds.graph.project($graph_name, s, t) AS g ",
    "reverse": "WITH gds.graph.project($graph_name, t, s) AS g ",
    "undirected": (
        "WITH gds.graph.project($graph_name, s, t, {}, {undirectedRelationshipTypes: ['*']}) AS g "
    ),
}
_NODE_ROW = (
    "WITH gds.util.asNode(nodeId) AS n, __VALUE__ RETURN n.uuid AS uuid, n.group_id AS group_id, "
)


def project_template_name(orientation: str) -> str:
    return f"gds_project_{orientation}_v1"


GDS_TEMPLATES: tuple[QueryTemplate, ...] = (
    QueryTemplate(
        "gds_scope_size_v1",
        TemplateKind.READ,
        _SCOPED + "WITH collect(DISTINCT s) + collect(DISTINCT t) AS ends, count(r) AS rels "
        "UNWIND ends AS e WITH rels, count(DISTINCT e) AS nodes "
        "RETURN nodes, rels",
    ),
    *(
        QueryTemplate(
            project_template_name(orientation),
            TemplateKind.GDS_CATALOG,
            _SCOPED
            + "WITH s, t LIMIT $max_relationships "
            + _PROJECT[orientation]
            + "RETURN g.graphName AS graph_name, g.nodeCount AS node_count, "
            "g.relationshipCount AS relationship_count",
        )
        for orientation in ORIENTATIONS
    ),
    QueryTemplate(
        "gds_drop_v1",
        TemplateKind.GDS_CATALOG,
        "CALL gds.graph.drop($graph_name, false) YIELD graphName RETURN graphName",
    ),
    QueryTemplate(
        "gds_catalog_list_v1",
        TemplateKind.READ,
        "CALL gds.graph.list() YIELD graphName WHERE graphName STARTS WITH $prefix "
        "RETURN collect(graphName) AS names",
    ),
    QueryTemplate(
        "gds_pagerank_stream_v1",
        TemplateKind.GDS_STREAM,
        "CALL gds.pageRank.stream($graph_name, {concurrency: 1}) YIELD nodeId, score "
        + _NODE_ROW.replace("__VALUE__", "score")
        + "score ORDER BY score DESC, uuid LIMIT $limit",
    ),
    QueryTemplate(
        "gds_degree_stream_v1",
        TemplateKind.GDS_STREAM,
        "CALL gds.degree.stream($graph_name, {concurrency: 1}) YIELD nodeId, score "
        + _NODE_ROW.replace("__VALUE__", "score")
        + "score ORDER BY score DESC, uuid LIMIT $limit",
    ),
    QueryTemplate(
        "gds_betweenness_stream_v1",
        TemplateKind.GDS_STREAM,
        "CALL gds.betweenness.stream($graph_name, {concurrency: 1}) YIELD nodeId, score "
        + _NODE_ROW.replace("__VALUE__", "score")
        + "score ORDER BY score DESC, uuid LIMIT $limit",
    ),
    QueryTemplate(
        "gds_louvain_stream_v1",
        TemplateKind.GDS_STREAM,
        "CALL gds.louvain.stream($graph_name, {concurrency: 1}) YIELD nodeId, communityId "
        + _NODE_ROW.replace("__VALUE__", "communityId")
        + "communityId AS community_id ORDER BY community_id, uuid LIMIT $limit",
    ),
    QueryTemplate(
        "gds_leiden_stream_v1",
        TemplateKind.GDS_STREAM,
        "CALL gds.leiden.stream($graph_name, {concurrency: 1, randomSeed: $random_seed}) "
        "YIELD nodeId, communityId "
        + _NODE_ROW.replace("__VALUE__", "communityId")
        + "communityId AS community_id ORDER BY community_id, uuid LIMIT $limit",
    ),
    QueryTemplate(
        "gds_fastrp_stream_v1",
        TemplateKind.GDS_STREAM,
        "CALL gds.fastRP.stream($graph_name, {embeddingDimension: $embedding_dimension, "
        "randomSeed: $random_seed, concurrency: 1}) YIELD nodeId, embedding "
        + _NODE_ROW.replace("__VALUE__", "embedding")
        + "embedding ORDER BY uuid LIMIT $limit",
    ),
    QueryTemplate(
        "link_candidates_v1",
        TemplateKind.READ,
        "MATCH (a:Entity {uuid: $anchor_uuid}) WHERE a.group_id IN $group_ids "
        "MATCH (a)-[r1:RELATES_TO]-(m:Entity)-[r2:RELATES_TO]-(c:Entity) "
        "WHERE c <> a AND m.group_id IN $group_ids AND c.group_id IN $group_ids "
        "AND r1.group_id IN $group_ids AND r2.group_id IN $group_ids "
        "AND type(r1) IN $relationship_types AND type(r2) IN $relationship_types "
        "AND NOT EXISTS { MATCH (a)-[x:RELATES_TO]-(c) WHERE x.group_id IN $group_ids } "
        "WITH DISTINCT c, m LIMIT $candidate_budget "
        "CALL (m) { MATCH (m)-[d:RELATES_TO]-(k:Entity) "
        "WHERE d.group_id IN $group_ids AND k.group_id IN $group_ids "
        "RETURN count(DISTINCT k) AS degree } "
        "RETURN c.uuid AS uuid, c.group_id AS group_id, collect(degree) AS common_degrees",
    ),
)
