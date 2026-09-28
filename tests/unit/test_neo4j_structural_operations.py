# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_neo4j_structural_operations.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""Neo4j adapter structural operations with a scripted driver (ADR-087)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
)
from l9_graphite_memory.adapters.neo4j_graph_templates import (
    DIRECTIONS,
    MAX_TEMPLATE_DEPTH,
    STRUCTURAL_TEMPLATES,
    expand_template_name,
    lucene_escape,
    shortest_path_template_name,
)
from l9_graphite_memory.errors import GraphQueryPolicyViolation
from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphLimits,
    GraphOperation,
    GraphProviderRequest,
)
from tests.graph_fakes import FakeNeo4jDriver

GROUP = graph_group_id("tenant-a", "shared")


class _Native:
    def __init__(self, value: datetime) -> None:
        self._value = value

    def to_native(self) -> datetime:
        return self._value


def _adapter(responses) -> tuple[Neo4jGraphIntelligence, FakeNeo4jDriver]:
    driver = FakeNeo4jDriver(responses=responses)
    adapter = Neo4jGraphIntelligence(
        Neo4jGraphIntelligenceConfig(uri="bolt://graph.invalid:7687"), driver_factory=lambda: driver
    )
    driver.bind(adapter)
    return adapter, driver


def _request(operation=GraphOperation.NEIGHBORHOOD, **overrides) -> GraphProviderRequest:
    values = {
        "operation": operation,
        "group_ids": (GROUP,),
        "anchor": GraphAnchor(entity_uuid=uuid4()),
        "relationship_types": ("RELATES_TO",),
        "limits": GraphLimits(max_depth=2),
        "operation_id": "unit",
    }
    values.update(overrides)
    return GraphProviderRequest(**values)


def _node(uuid, name="n"):
    return {"uuid": str(uuid), "group_id": GROUP, "name": name, "labels": ["Entity"]}


def test_every_direction_and_depth_has_a_registered_audited_template() -> None:
    names = {template.name for template in STRUCTURAL_TEMPLATES}
    for direction in DIRECTIONS:
        for depth in range(1, MAX_TEMPLATE_DEPTH + 1):
            assert expand_template_name(direction, depth) in names
            assert shortest_path_template_name(direction, depth) in names
    assert "*1..7" not in " ".join(template.cypher for template in STRUCTURAL_TEMPLATES)


def test_depth_zero_returns_anchor_only_without_expansion() -> None:
    anchor = uuid4()
    adapter, driver = _adapter(
        {
            "anchor_entities_v1": [{"nodes": [_node(anchor, "Falcon")], "edges": []}],
            "entity_supporting_episodes_v1": [{"uuid": str(anchor), "episodes": []}],
        }
    )
    result = adapter.neighborhood(
        _request(anchor=GraphAnchor(entity_uuid=anchor), limits=GraphLimits(max_depth=0))
    )
    assert [n.name for n in result.nodes] == ["Falcon"]
    assert not any(call.template.startswith("expand_") for call in driver.calls)


def test_expansion_binds_scope_filters_and_budget_as_parameters() -> None:
    a, b, episode, record = uuid4(), uuid4(), uuid4(), uuid4()
    as_of = datetime(2026, 9, 1, tzinfo=timezone.utc)
    adapter, driver = _adapter(
        {
            "anchor_entities_v1": [{"nodes": [_node(a)], "edges": []}],
            "expand_both_d2_v1": [
                {
                    "nodes": [_node(a), _node(b)],
                    "edges": [
                        {
                            "uuid": str(uuid4()),
                            "source": str(a),
                            "target": str(b),
                            "type": "RELATES_TO",
                            "group_id": GROUP,
                            "fact": "a knows b",
                            "valid_at": _Native(as_of),
                            "invalid_at": None,
                            "episodes": [str(episode), "not-a-uuid"],
                        }
                    ],
                }
            ],
            "entity_supporting_episodes_v1": [
                {"uuid": str(a), "episodes": [str(record)]},
                {"uuid": str(b), "episodes": []},
            ],
            # Edge episode uuids map to the record id in the episode name.
            "episode_support_ids_v1": [{"uuid": str(episode), "support": str(record)}],
        }
    )
    result = adapter.neighborhood(
        _request(
            anchor=GraphAnchor(entity_uuid=a),
            as_of=as_of,
            limits=GraphLimits(max_depth=2, max_edges=9),
        )
    )
    expand = next(call for call in driver.calls if call.template == "expand_both_d2_v1")
    assert expand.parameters["group_ids"] == [GROUP]
    assert expand.parameters["relationship_types"] == ["RELATES_TO"]
    assert expand.parameters["as_of"] == as_of
    assert expand.parameters["path_budget"] == 10
    assert expand.parameters["anchor_uuids"] == [str(a)]
    assert all(call.session_config["default_access_mode"] == "READ" for call in driver.calls)
    edge = result.edges[0]
    assert edge.valid_at == as_of
    assert edge.supporting_episode_ids == (record,)
    assert {n.entity_uuid: n.supporting_episode_ids for n in result.nodes}[a] == (record,)
    support = next(call for call in driver.calls if call.template == "episode_support_ids_v1")
    assert support.parameters["group_ids"] == [GROUP]
    assert sorted(support.parameters["episode_uuids"]) == sorted([str(episode), "not-a-uuid"])


def test_traverse_follows_direction_and_neighborhood_ignores_it() -> None:
    anchor = uuid4()
    responses = {
        "anchor_entities_v1": [{"nodes": [_node(anchor)], "edges": []}],
        "expand_out_d1_v1": [],
        "expand_both_d1_v1": [],
        "entity_supporting_episodes_v1": [],
    }
    adapter, driver = _adapter(responses)
    request = _request(
        anchor=GraphAnchor(entity_uuid=anchor), direction="out", limits=GraphLimits(max_depth=1)
    )
    adapter.traverse(request)
    adapter.neighborhood(request)
    templates = [call.template for call in driver.calls]
    assert "expand_out_d1_v1" in templates and "expand_both_d1_v1" in templates


def test_record_and_text_anchors_resolve_through_scoped_templates() -> None:
    record, entity = uuid4(), uuid4()
    adapter, driver = _adapter(
        {
            "episode_entities_v1": [{"uuid": str(entity)}],
            "entity_lookup_v1": [{"uuid": str(entity)}],
            "anchor_entities_v1": [{"nodes": [_node(entity)], "edges": []}],
            "entity_supporting_episodes_v1": [],
        }
    )
    adapter.neighborhood(
        _request(anchor=GraphAnchor(record_id=record), limits=GraphLimits(max_depth=0))
    )
    adapter.neighborhood(
        _request(anchor=GraphAnchor(query="Falcon) OR (x:Y"), limits=GraphLimits(max_depth=0))
    )
    by_template = {call.template: call for call in driver.calls}
    assert by_template["episode_entities_v1"].parameters["record_id"] == str(record)
    assert by_template["episode_entities_v1"].parameters["group_ids"] == [GROUP]
    lookup = by_template["entity_lookup_v1"].parameters
    assert lookup["query"] == r"Falcon\) or \(x\:Y"
    assert lookup["group_ids"] == [GROUP]


def test_expansion_budget_exhaustion_marks_truncation() -> None:
    anchor = uuid4()
    rows = [{"nodes": [_node(anchor), _node(uuid4())], "edges": []} for _ in range(3)]
    adapter, _driver = _adapter(
        {
            "anchor_entities_v1": [{"nodes": [_node(anchor)], "edges": []}],
            "expand_both_d1_v1": rows,
            "entity_supporting_episodes_v1": [],
        }
    )
    result = adapter.neighborhood(
        _request(
            anchor=GraphAnchor(entity_uuid=anchor), limits=GraphLimits(max_depth=1, max_edges=2)
        )
    )
    assert result.truncated


def test_path_requires_depth_and_both_anchors() -> None:
    adapter, _driver = _adapter({})
    with pytest.raises(GraphQueryPolicyViolation, match="max_depth"):
        adapter.path(
            _request(
                GraphOperation.PATH,
                target=GraphAnchor(entity_uuid=uuid4()),
                limits=GraphLimits(max_depth=0),
            )
        )
    with pytest.raises(GraphQueryPolicyViolation, match="anchor"):
        adapter.path(_request(GraphOperation.PATH, target=None))


def test_path_rows_become_ordered_paths() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    e1, e2 = uuid4(), uuid4()
    row = {
        "nodes": [_node(a), _node(b), _node(c)],
        "edges": [
            {
                "uuid": str(e1),
                "source": str(a),
                "target": str(b),
                "type": "RELATES_TO",
                "group_id": GROUP,
            },
            {
                "uuid": str(e2),
                "source": str(b),
                "target": str(c),
                "type": "RELATES_TO",
                "group_id": GROUP,
            },
        ],
    }
    adapter, driver = _adapter(
        {"shortest_path_both_d3_v1": [row], "entity_supporting_episodes_v1": []}
    )
    result = adapter.path(
        _request(
            GraphOperation.PATH,
            anchor=GraphAnchor(entity_uuid=a),
            target=GraphAnchor(entity_uuid=c),
            limits=GraphLimits(max_depth=3, max_paths=4),
        )
    )
    assert result.paths[0].node_uuids == (a, b, c)
    assert result.paths[0].edge_uuids == (e1, e2)
    assert result.paths[0].length == 2
    call = next(c for c in driver.calls if c.template == "shortest_path_both_d3_v1")
    assert call.parameters["path_budget"] == 5
    assert call.parameters["target_uuids"] == [str(c)]


def test_lucene_escape_neutralizes_query_syntax() -> None:
    assert lucene_escape('a+b "c" AND d*') == r"a\+b \"c\" and d\*"


def test_adapter_serves_the_baseline_structural_capabilities() -> None:
    from tests.graph_fakes import healthy_graphiti_responses

    adapter, _driver = _adapter(healthy_graphiti_responses())
    served = {capability.value for capability in adapter.capabilities()}
    assert {"graph.traverse", "graph.path", "graph.neighborhood"} <= served
