# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_neo4j_gds_operations.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""GDS analytics lifecycle with a scripted driver (ADR-088, GI-018/020/021)."""

from __future__ import annotations

from uuid import uuid4

import pytest

from l9_graphite_memory.adapters.neo4j_gds_templates import GDS_TEMPLATES
from l9_graphite_memory.adapters.neo4j_graph_intelligence import (
    Neo4jGraphIntelligence,
    Neo4jGraphIntelligenceConfig,
    _adamic_adar,
    _resource_allocation,
)
from l9_graphite_memory.errors import GraphQueryPolicyViolation
from l9_graphite_memory.graph import graph_group_id
from l9_graphite_memory.graph.contracts import (
    GraphAnchor,
    GraphLimits,
    GraphOperation,
    GraphProviderRequest,
    GraphReceiptStatus,
)
from tests.graph_fakes import FakeNeo4jDriver

GROUP = graph_group_id("tenant-a", "shared")


def _adapter(responses, **config) -> tuple[Neo4jGraphIntelligence, FakeNeo4jDriver]:
    driver = FakeNeo4jDriver(responses=responses)
    adapter = Neo4jGraphIntelligence(
        Neo4jGraphIntelligenceConfig(uri="bolt://graph.invalid:7687", **config),
        driver_factory=lambda: driver,
    )
    driver.bind(adapter)
    return adapter, driver


def _request(operation=GraphOperation.CENTRALITY, **overrides) -> GraphProviderRequest:
    values = {
        "operation": operation,
        "group_ids": (GROUP,),
        "relationship_types": ("RELATES_TO",),
        "limits": GraphLimits(max_nodes=10),
        "algorithm_id": "pagerank",
        "operation_id": "0123456789abcdef0123",
    }
    values.update(overrides)
    return GraphProviderRequest(**values)


def _analytics_responses(stream_rows, *, nodes=3, rels=3, drop=None):
    entity_rows = [
        {"nodes": [{"uuid": row["uuid"], "group_id": GROUP, "name": "n", "labels": ["Entity"]}]}
        for row in stream_rows
    ]
    return {
        "gds_scope_size_v1": [{"nodes": nodes, "rels": rels}],
        "gds_project_natural_v1": [
            {"graph_name": "x", "node_count": nodes, "relationship_count": rels}
        ],
        "gds_project_reverse_v1": [
            {"graph_name": "x", "node_count": nodes, "relationship_count": rels}
        ],
        "gds_project_undirected_v1": [
            {"graph_name": "x", "node_count": nodes, "relationship_count": rels * 2}
        ],
        "gds_pagerank_stream_v1": stream_rows,
        "gds_leiden_stream_v1": stream_rows,
        "gds_louvain_stream_v1": stream_rows,
        "gds_fastrp_stream_v1": stream_rows,
        "gds_drop_v1": drop if drop is not None else [{"graphName": "x"}],
        "anchor_entities_v1": lambda params: [
            row for row in entity_rows if row["nodes"][0]["uuid"] in params["anchor_uuids"]
        ],
        "entity_supporting_episodes_v1": [],
    }


def test_no_gds_template_can_write_mutate_or_export() -> None:
    for template in GDS_TEMPLATES:
        lowered = template.cypher.lower()
        assert ".write" not in lowered and ".mutate" not in lowered and "export" not in lowered


def test_projection_is_streamed_then_dropped_with_an_opaque_name() -> None:
    rows = [{"uuid": str(uuid4()), "group_id": GROUP, "score": 0.5}]
    adapter, driver = _adapter(_analytics_responses(rows))
    result = adapter.centrality(_request(direction="out"))
    templates = [call.template for call in driver.calls]
    project, stream, drop = (
        templates.index("gds_project_natural_v1"),
        templates.index("gds_pagerank_stream_v1"),
        templates.index("gds_drop_v1"),
    )
    assert project < stream < drop
    name = next(c for c in driver.calls if c.template == "gds_drop_v1").parameters["graph_name"]
    assert name.startswith("l9gi_0123456789abcdef_")
    assert "tenant" not in name and "shared" not in name
    assert all(call.session_config["default_access_mode"] == "READ" for call in driver.calls)
    assert result.provider_metadata["catalog_cleanup"] == "dropped"
    assert result.scores[0].score == 0.5


def test_catalog_graph_is_dropped_when_the_stream_raises() -> None:
    responses = _analytics_responses([])
    responses["gds_pagerank_stream_v1"] = RuntimeError("stream failed")
    adapter, driver = _adapter(responses)
    with pytest.raises(RuntimeError, match="stream failed"):
        adapter.centrality(_request())
    assert "gds_drop_v1" in [call.template for call in driver.calls]


def test_drop_failure_is_reported_and_marks_the_receipt_partial() -> None:
    from l9_graphite_memory.graph.contracts import GraphIntelligenceRequest
    from l9_graphite_memory.graph.ports import GraphCapability
    from l9_graphite_memory.graph.service import GraphIntelligenceService
    from tests.graph_fakes import FakeGraphPort, seeded_memory

    service, store, principal, write = seeded_memory()
    record = write("tenant-a", "fact")
    rows = [{"uuid": str(uuid4()), "group_id": GROUP, "score": 0.5}]
    responses = _analytics_responses(rows, drop=RuntimeError("drop failed"))
    responses["entity_supporting_episodes_v1"] = [
        {"uuid": rows[0]["uuid"], "episodes": [str(record)]}
    ]
    adapter, _driver = _adapter(responses)
    result = adapter.centrality(_request())
    assert result.provider_metadata["catalog_cleanup"] == "failed"
    assert adapter.catalog_cleanup_failures == 1

    port = FakeGraphPort(
        {GraphOperation.CENTRALITY: result}, capabilities=(GraphCapability.CENTRALITY,)
    )
    receipt = GraphIntelligenceService(
        store, port, namespace_policy=service.namespace_policy
    ).execute(
        principal("tenant-a"),
        GraphIntelligenceRequest(operation=GraphOperation.CENTRALITY, namespaces=("shared",)),
    )
    assert receipt.status is GraphReceiptStatus.PARTIAL
    assert {"class": "gds_catalog_cleanup_failed", "stage": "provider"} in receipt.failures


def test_scope_over_the_analytics_ceiling_is_refused_before_projection() -> None:
    adapter, driver = _adapter(_analytics_responses([], nodes=11), gds_max_nodes=10)
    with pytest.raises(GraphQueryPolicyViolation, match="ceiling"):
        adapter.centrality(_request())
    assert not any(call.template.startswith("gds_project") for call in driver.calls)


def test_empty_scope_projects_nothing() -> None:
    adapter, driver = _adapter(_analytics_responses([], rels=0))
    result = adapter.centrality(_request())
    assert result.scores == ()
    assert not any(call.template.startswith("gds_project") for call in driver.calls)


def test_leiden_requires_an_undirected_projection() -> None:
    adapter, _driver = _adapter(_analytics_responses([]))
    with pytest.raises(GraphQueryPolicyViolation, match="undirected"):
        adapter.community(
            _request(GraphOperation.COMMUNITY, algorithm_id="leiden", direction="out")
        )


def test_orientation_follows_direction_and_leiden_projects_undirected() -> None:
    rows = [{"uuid": str(uuid4()), "group_id": GROUP, "score": 1.0, "community_id": 3}]
    adapter, driver = _adapter(_analytics_responses(rows))
    adapter.centrality(_request(direction="in"))
    adapter.community(_request(GraphOperation.COMMUNITY, algorithm_id="leiden"))
    templates = [call.template for call in driver.calls]
    assert "gds_project_reverse_v1" in templates and "gds_project_undirected_v1" in templates


def test_unknown_algorithm_ids_are_refused() -> None:
    adapter, _driver = _adapter(_analytics_responses([]))
    with pytest.raises(GraphQueryPolicyViolation):
        adapter.centrality(_request(algorithm_id="gds.pageRank.write"))
    with pytest.raises(GraphQueryPolicyViolation):
        adapter.community(_request(GraphOperation.COMMUNITY, algorithm_id="labelPropagation"))


def test_similarity_ranks_by_cosine_and_excludes_the_anchor() -> None:
    anchor, near, far = str(uuid4()), str(uuid4()), str(uuid4())
    rows = [
        {"uuid": anchor, "group_id": GROUP, "embedding": [1.0, 0.0]},
        {"uuid": near, "group_id": GROUP, "embedding": [0.9, 0.1]},
        {"uuid": far, "group_id": GROUP, "embedding": [0.0, 1.0]},
    ]
    adapter, _driver = _adapter(_analytics_responses(rows))
    result = adapter.structural_similarity(
        _request(
            GraphOperation.STRUCTURAL_SIMILARITY,
            algorithm_id="fastrp-cosine",
            anchor=GraphAnchor(entity_uuid=anchor),
        )
    )
    assert [str(score.entity_uuid) for score in result.scores] == [near, far]
    assert all(str(score.target_uuid) == anchor for score in result.scores)


def test_link_prediction_scores_in_scope_and_materializes_nothing() -> None:
    anchor, strong, weak = str(uuid4()), str(uuid4()), str(uuid4())
    responses = {
        "link_candidates_v1": [
            {"uuid": weak, "group_id": GROUP, "common_degrees": [10]},
            {"uuid": strong, "group_id": GROUP, "common_degrees": [2, 3]},
        ],
        "anchor_entities_v1": [
            {
                "nodes": [
                    {"uuid": u, "group_id": GROUP, "name": "n", "labels": ["Entity"]}
                    for u in (anchor, strong, weak)
                ]
            }
        ],
        "entity_supporting_episodes_v1": [],
    }
    adapter, driver = _adapter(responses, link_prediction_enabled=True)
    result = adapter.link_prediction(
        _request(
            GraphOperation.LINK_PREDICTION,
            algorithm_id="adamic-adar",
            anchor=GraphAnchor(entity_uuid=anchor),
        )
    )
    assert [str(score.target_uuid) for score in result.scores] == [strong, weak]
    assert result.scores[0].score == pytest.approx(_adamic_adar([2, 3]))
    call = next(c for c in driver.calls if c.template == "link_candidates_v1")
    assert call.parameters["group_ids"] == [GROUP]
    assert _resource_allocation([2, 4]) == pytest.approx(0.75)


def test_stale_catalog_sweep_drops_every_prefixed_graph() -> None:
    adapter, driver = _adapter(
        {
            "gds_catalog_list_v1": [{"names": ["l9gi_a", "l9gi_b"]}],
            "gds_drop_v1": [{"graphName": "x"}],
        }
    )
    assert adapter.cleanup_stale_catalog() == 2
    assert driver.calls[0].parameters == {"prefix": "l9gi_"}


def test_link_prediction_is_unavailable_at_the_adapter_when_disabled() -> None:
    from l9_graphite_memory.errors import GraphCapabilityUnavailable

    adapter, driver = _adapter({})
    with pytest.raises(GraphCapabilityUnavailable, match="disabled"):
        adapter.link_prediction(
            _request(
                GraphOperation.LINK_PREDICTION,
                algorithm_id="adamic-adar",
                anchor=GraphAnchor(entity_uuid=uuid4()),
            )
        )
    assert driver.calls == []
