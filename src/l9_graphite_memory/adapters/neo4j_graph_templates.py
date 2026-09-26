# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: src/l9_graphite_memory/adapters/neo4j_graph_templates.py
#   layer: adapter
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Static structural Cypher templates over the Graphiti Neo4j schema (ADR-087).

Graphiti v0.30.2 stores entities as ``(:Entity {uuid, group_id, name,
summary})``, entity relationships as ``-[:RELATES_TO {uuid, group_id, fact,
episodes, valid_at, invalid_at, created_at, expired_at}]->``, and episode
provenance as ``(:Episodic)-[:MENTIONS]->(:Entity)``.

Cypher cannot bind a variable-length bound as a parameter, so each bounded
depth is its own template. The family is expanded once, at import, from
module constants into a closed set of registered statements; every generated
text passes the registration audit and no request value ever reaches the
query text. Request values — anchors, groups, relationship types, temporal
coordinates, limits — are bound parameters only.
"""

from __future__ import annotations

from .neo4j_query_policy import QueryTemplate, TemplateKind

MAX_TEMPLATE_DEPTH = 6
DIRECTIONS = ("out", "in", "both")
_PATTERN = {
    "out": "-[rels:RELATES_TO*1..__DEPTH__]->",
    "in": "<-[rels:RELATES_TO*1..__DEPTH__]-",
    "both": "-[rels:RELATES_TO*1..__DEPTH__]-",
}
_SHORTEST = {
    "out": "-[rels:RELATES_TO*..__DEPTH__]->",
    "in": "<-[rels:RELATES_TO*..__DEPTH__]-",
    "both": "-[rels:RELATES_TO*..__DEPTH__]-",
}

# Relationship admission: allowlisted type, authorized group, valid at
# ``as_of`` (valid time), and current as of ``recorded_before`` (transaction
# time; without it, edges Graphiti has expired are excluded).
_EDGE_FILTER = (
    "all(r IN rels WHERE type(r) IN $relationship_types AND r.group_id IN $group_ids "
    "AND ($as_of IS NULL OR ((r.valid_at IS NULL OR r.valid_at <= $as_of) "
    "AND (r.invalid_at IS NULL OR r.invalid_at > $as_of))) "
    "AND (CASE WHEN $recorded_before IS NULL THEN r.expired_at IS NULL "
    "ELSE ((r.created_at IS NULL OR r.created_at <= $recorded_before) "
    "AND (r.expired_at IS NULL OR r.expired_at > $recorded_before)) END)) "
    "AND all(x IN nodes(p) WHERE x.group_id IN $group_ids)"
)
# Canonical support identity of an episode (ADR-090): the record id carried
# in its ``memory:<record_id>`` name, else its provider uuid (episodes created
# under the legacy ``uuid = record_id`` convention).
_SUPPORT_ID = "CASE WHEN ep.name STARTS WITH 'memory:' THEN substring(ep.name, 7) ELSE ep.uuid END"
_NODE_MAP = "{uuid: x.uuid, group_id: x.group_id, name: x.name, labels: labels(x)}"
_EDGE_MAP = (
    "{uuid: r.uuid, source: startNode(r).uuid, target: endNode(r).uuid, type: type(r), "
    "group_id: r.group_id, fact: r.fact, valid_at: r.valid_at, invalid_at: r.invalid_at, "
    "episodes: coalesce(r.episodes, [])[..$support_limit]}"
)

_EXPAND = (
    "MATCH (a:Entity) WHERE a.uuid IN $anchor_uuids AND a.group_id IN $group_ids "
    "MATCH p = (a)__PATTERN__(n:Entity) WHERE __FILTER__ "
    "WITH p LIMIT $path_budget "
    "RETURN [x IN nodes(p) | __NODE__] AS nodes, [r IN relationships(p) | __EDGE__] AS edges"
)
_SHORTEST_PATHS = (
    "MATCH (a:Entity) WHERE a.uuid IN $anchor_uuids AND a.group_id IN $group_ids "
    "MATCH (b:Entity) WHERE b.uuid IN $target_uuids AND b.group_id IN $group_ids AND a <> b "
    "MATCH p = allShortestPaths((a)__PATTERN__(b)) WHERE __FILTER__ "
    "WITH p LIMIT $path_budget "
    "RETURN [x IN nodes(p) | __NODE__] AS nodes, [r IN relationships(p) | __EDGE__] AS edges"
)


def _render(body: str, pattern: str, depth: int) -> str:
    return (
        body.replace("__PATTERN__", pattern.replace("__DEPTH__", str(depth)))
        .replace("__FILTER__", _EDGE_FILTER)
        .replace("__NODE__", _NODE_MAP)
        .replace("__EDGE__", _EDGE_MAP)
    )


def expand_template_name(direction: str, depth: int) -> str:
    return f"expand_{direction}_d{depth}_v1"


def shortest_path_template_name(direction: str, depth: int) -> str:
    return f"shortest_path_{direction}_d{depth}_v1"


STRUCTURAL_TEMPLATES: tuple[QueryTemplate, ...] = (
    QueryTemplate(
        "anchor_entities_v1",
        TemplateKind.READ,
        "MATCH (x:Entity) WHERE x.uuid IN $anchor_uuids AND x.group_id IN $group_ids "
        f"RETURN collect({_NODE_MAP}) AS nodes, [] AS edges",
    ),
    QueryTemplate(
        "episode_entities_v1",
        TemplateKind.READ,
        "MATCH (ep:Episodic) WHERE ep.group_id IN $group_ids "
        "AND (ep.name = $episode_name OR ep.uuid = $record_id) "
        "MATCH (ep)-[m:MENTIONS]->(n:Entity) WHERE n.group_id IN $group_ids "
        "RETURN DISTINCT n.uuid AS uuid ORDER BY uuid LIMIT $limit",
    ),
    QueryTemplate(
        "entity_lookup_v1",
        TemplateKind.READ,
        "CALL db.index.fulltext.queryNodes('node_name_and_summary', $query, {limit: $scan_limit}) "
        "YIELD node, score WHERE node.group_id IN $group_ids "
        "RETURN node.uuid AS uuid ORDER BY score DESC, uuid LIMIT $limit",
    ),
    QueryTemplate(
        "entity_supporting_episodes_v1",
        TemplateKind.READ,
        "UNWIND $entity_uuids AS id MATCH (n:Entity {uuid: id}) WHERE n.group_id IN $group_ids "
        "OPTIONAL MATCH (ep:Episodic)-[:MENTIONS]->(n) WHERE ep.group_id IN $group_ids "
        f"WITH n, {_SUPPORT_ID} AS support ORDER BY support "
        "RETURN n.uuid AS uuid, collect(DISTINCT support)[..$support_limit] AS episodes",
    ),
    QueryTemplate(
        "episode_support_ids_v1",
        TemplateKind.READ,
        "UNWIND $episode_uuids AS id MATCH (ep:Episodic {uuid: id}) "
        "WHERE ep.group_id IN $group_ids "
        f"RETURN ep.uuid AS uuid, {_SUPPORT_ID} AS support",
    ),
    *(
        QueryTemplate(
            expand_template_name(direction, depth),
            TemplateKind.READ,
            _render(_EXPAND, _PATTERN[direction], depth),
        )
        for direction in DIRECTIONS
        for depth in range(1, MAX_TEMPLATE_DEPTH + 1)
    ),
    *(
        QueryTemplate(
            shortest_path_template_name(direction, depth),
            TemplateKind.READ,
            _render(_SHORTEST_PATHS, _SHORTEST[direction], depth),
        )
        for direction in DIRECTIONS
        for depth in range(1, MAX_TEMPLATE_DEPTH + 1)
    ),
)


_LUCENE_SPECIALS = set('+-&|!(){}[]^"~*?:\\/')


def lucene_escape(text: str) -> str:
    """Escape Lucene query syntax so text anchors are literal terms."""

    escaped = "".join(f"\\{ch}" if ch in _LUCENE_SPECIALS else ch for ch in text)
    # Bare boolean operators would be read as syntax; lower-case them.
    return " ".join(
        word.lower() if word in {"AND", "OR", "NOT", "TO"} else word for word in escaped.split()
    )
