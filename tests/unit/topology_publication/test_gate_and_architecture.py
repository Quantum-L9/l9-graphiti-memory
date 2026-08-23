# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/topology_publication/test_gate_and_architecture.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Gate intent conformance with zero dispatch, and the WS18 architecture wall.

The adapter must keep local plan execution compatible with future Gate
transport (every eligible intent validates against the Gate boundary's own
contract) without ever instantiating a Gate client, selecting a destination,
or acquiring a second canonical write path. The architecture test is AST-based
so a regression fails in CI before review.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import l9_graphite_memory.ingestion.topology_publication as adapter_module
from l9_graphite_memory.ingestion import (
    TopologyPlanError,
    load_publication_plan,
    load_verified_bundle,
    validate_publication_inputs,
)
from tests.unit.topology_publication.conftest import (
    make_candidate,
    make_plan_bundle,
    make_topology_bundle,
)

ADAPTER_PATH = Path(adapter_module.__file__)

FORBIDDEN_IMPORT_PREFIXES = (
    "l9_graphite_memory.adapters",
    "l9_graphite_memory.zep_transport",
    "l9_graphite_memory.transport",
    "sqlite3",
    "psycopg2",
    "asyncpg",
)
FORBIDDEN_CALL_ATTRIBUTES = {
    "commit_write",
    "commit_deletion",
    "commit_archive",
    "commit_projection_rebuild",
    "save_phase_lock",
    "dispatch",
    "dispatch_root",
    "dispatch_follow_up",
    "connect",
    "execute",
    "executemany",
}


def test_eligible_intents_conform_to_the_gate_contract(tmp_path: Path, topology_principal) -> None:
    plan_root = make_plan_bundle(
        tmp_path / "plan", [make_candidate(candidate_id="c-1", status="eligible")]
    )
    topo_root = make_topology_bundle(tmp_path / "topo")
    plan = load_publication_plan(load_verified_bundle(plan_root))
    validate_publication_inputs(plan, load_verified_bundle(topo_root))


def test_gate_conformance_is_enforced_not_assumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Gate validator is actually consulted for every eligible intent.

    Canonical-valid intents are Gate-valid by shared contract, so the negative
    path is proven by making the Gate boundary refuse and observing the plan
    fail — if the adapter ever stopped calling the validator, this would pass
    validation and the test would fail.
    """
    plan_root = make_plan_bundle(
        tmp_path / "plan", [make_candidate(candidate_id="c-1", status="eligible")]
    )
    plan = load_publication_plan(load_verified_bundle(plan_root))
    topo = load_verified_bundle(make_topology_bundle(tmp_path / "topo"))

    def refuse(value: object) -> object:
        raise ValueError("gate boundary refused this intent")

    monkeypatch.setattr(
        adapter_module.GateMemoryBridge, "validate_intent", staticmethod(refuse)
    )
    with pytest.raises(TopologyPlanError, match="Gate intent conformance"):
        validate_publication_inputs(plan, topo)


def test_adapter_module_imports_no_store_projection_or_transport() -> None:
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for name in names:
            if name.startswith(FORBIDDEN_IMPORT_PREFIXES):
                violations.append(name)
    assert violations == []


def test_adapter_module_never_calls_guarded_store_or_dispatch_methods() -> None:
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in FORBIDDEN_CALL_ATTRIBUTES:
                violations.append(node.func.attr)
    assert violations == []


def test_adapter_only_service_call_is_memory_service_write() -> None:
    tree = ast.parse(ADAPTER_PATH.read_text(encoding="utf-8"))
    service_calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = node.func.value
            if isinstance(target, ast.Name) and target.id == "memory_service":
                service_calls.add(node.func.attr)
    assert service_calls == {"write"}


def test_adapter_module_references_no_peer_urls() -> None:
    text = ADAPTER_PATH.read_text(encoding="utf-8")
    assert "http://" not in text
    assert "https://" not in text
    assert "peer_url" not in text
