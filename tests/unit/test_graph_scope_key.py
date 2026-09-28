# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_graph_scope_key.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""GraphScopeKey v1 derivation (ADR-084)."""

from __future__ import annotations

import hashlib
import re

import pytest

from l9_graphite_memory.graph import (
    GRAPH_SCOPE_SCHEME,
    graph_group_id,
    graph_group_ids,
    graph_scope_digest,
    graph_scope_material,
    is_graph_group_id,
)

# Graphiti v0.30.2 graphiti_core.helpers.validate_group_id accepts only this.
_GRAPHITI_GROUP_ID = re.compile(r"^[a-zA-Z0-9_-]+$")


def test_material_is_sorted_compact_canonical_json() -> None:
    assert graph_scope_material("tenant-a", "shared") == (
        b'{"namespace":"shared","tenant_id":"tenant-a"}'
    )


def test_group_id_matches_fixed_test_vector() -> None:
    expected = hashlib.sha256(b'{"namespace":"shared","tenant_id":"tenant-a"}').hexdigest()
    assert graph_scope_digest("tenant-a", "shared") == expected
    assert graph_group_id("tenant-a", "shared") == f"l9g-v1-{expected}"
    assert GRAPH_SCOPE_SCHEME == "l9g-v1"


def test_group_id_is_deterministic() -> None:
    assert graph_group_id("tenant-a", "repo") == graph_group_id("tenant-a", "repo")


def test_same_namespace_in_two_tenants_never_collides() -> None:
    assert graph_group_id("tenant-a", "shared") != graph_group_id("tenant-b", "shared")


def test_same_tenant_distinct_namespaces_never_collide() -> None:
    assert graph_group_id("tenant-a", "repo-a") != graph_group_id("tenant-a", "repo-b")


def test_component_boundary_is_unambiguous() -> None:
    # Naive concatenation would make these two scopes identical.
    assert graph_group_id("tenant-a", "b:c") != graph_group_id("tenant-a:b", "c")


def test_group_id_is_graphiti_safe_and_hides_raw_tenant() -> None:
    group_id = graph_group_id("Tenant Ümlaut/α", "ns with spaces")
    assert _GRAPHITI_GROUP_ID.fullmatch(group_id)
    assert is_graph_group_id(group_id)
    assert "Tenant" not in group_id
    assert "ns with spaces" not in group_id


@pytest.mark.parametrize(
    ("tenant_id", "namespace"),
    [("", "repo"), ("   ", "repo"), ("tenant-a", ""), ("tenant-a", "\t")],
)
def test_blank_scope_component_is_rejected(tenant_id: str, namespace: str) -> None:
    with pytest.raises(ValueError, match="graph scope"):
        graph_group_id(tenant_id, namespace)


def test_multi_namespace_derivation_is_exact_ordered_and_deduplicated() -> None:
    groups = graph_group_ids("tenant-a", ("repo-b", "repo-a", "repo-b"))
    assert groups == (graph_group_id("tenant-a", "repo-b"), graph_group_id("tenant-a", "repo-a"))


def test_bare_namespace_is_not_a_scope_key() -> None:
    assert not is_graph_group_id("shared")
    assert not is_graph_group_id("l9g:v1:" + "0" * 64)
