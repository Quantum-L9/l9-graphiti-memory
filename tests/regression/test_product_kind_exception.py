# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_product_kind_exception.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 3.0.0
#   updated: 2026-10-15

"""The hosted-Memory product-kind exception binds only exactly, and never relaxes.

``product-topology.yaml`` claims ``l9.product-kind-exception/memory-hosted-service@1``
(``Quantum-L9/.github`` Semantic Foundation v3.21.0; ADR-094, 2026-10-15). Every
positive here is paired with the hostile mutations that must fail it:

- the committed topology passes this repository's validator, the derived
  ProductManifest gate, and the canonical RC-029 evaluator shipped by the
  authority itself (``scripts/validate-semantics.py``), so the two never drift;
- a claim that does not resolve, is unadmitted, or is bound to another product,
  repository, archetype or registry entry fails; it is never ignored or coerced
  to plain Dependency law;
- the exception's positive obligations (remote protocol, authentication,
  authorization, identity dimensions, ``service_admitted``) cannot be dropped;
- Constellation identity, Gate admission and Constellation communication stay
  forbidden;
- exception models without the claim are a kind contradiction;
- a release below the exception's 3.0.0 floor is rejected.

These cases read global law from a ``Quantum-L9/.github`` checkout named by
``L9_SEMANTIC_AUTHORITY_ROOT``, which CI pins (release binding
``authority.revision``) for ``scripts/validate_release.sh``. Without it they
skip visibly; nothing from the authority is copied into this repository.
"""

from __future__ import annotations

import copy
import functools
import importlib.util
import os
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY = REPO_ROOT / "product-topology.yaml"
ASSURANCE = REPO_ROOT / "tools" / "assurance"
EXCEPTION_ID = "l9.product-kind-exception/memory-hosted-service@1"


def _authority() -> Path:
    raw = os.environ.get("L9_SEMANTIC_AUTHORITY_ROOT", "").strip()
    if not raw:
        pytest.skip("L9_SEMANTIC_AUTHORITY_ROOT is not set; kind-exception law cannot be read")
    root = Path(raw).resolve()
    if not (root / "semantics" / "product_kinds.yaml").is_file():
        pytest.skip(f"L9_SEMANTIC_AUTHORITY_ROOT has no semantics/: {root}")
    return root


def _module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


@pytest.fixture(scope="module")
def authority() -> Path:
    return _authority()


@pytest.fixture(scope="module")
def law() -> ModuleType:
    return _module("validate_product_topology", ASSURANCE / "validate_product_topology.py")


@pytest.fixture(scope="module")
def kinds(authority: Path) -> dict[str, Any]:
    return dict(yaml.safe_load((authority / "semantics" / "product_kinds.yaml").read_text()))


@pytest.fixture
def topology() -> dict[str, Any]:
    return dict(yaml.safe_load(TOPOLOGY.read_text(encoding="utf-8")))


def _validate(law: ModuleType, authority: Path, topo: dict[str, Any], tmp_path: Path, **kw: Any):
    path = tmp_path / "product-topology.yaml"
    path.write_text(yaml.safe_dump(topo, sort_keys=False), encoding="utf-8")
    return law.validate(REPO_ROOT, authority, path, **kw)


@functools.lru_cache(maxsize=1)
def _canonical_evaluator(authority: Path) -> tuple[ModuleType, dict[str, Any]]:
    vs = _module("validate_semantics_rc029", authority / "scripts" / "validate-semantics.py")
    report = vs.Report()
    docs = vs.check_sc001(authority, report)
    assert not report.failures, report.failures
    docs[vs.RC029_ADR_PATH] = (authority / vs.RC029_ADR_PATH).read_text(encoding="utf-8")
    return vs, docs


def _canonical_findings(authority: Path, topo: dict[str, Any]) -> list[tuple[str, str]]:
    """RC-029 coherence as the authority evaluates it, for the same topology."""

    vs, docs = _canonical_evaluator(authority)
    return list(vs._rc029_topology_coherence(docs, topo))


def test_the_committed_topology_binds_the_exception(law, authority, kinds, topology, tmp_path):
    assert topology["product"]["kind_exception_ref"] == EXCEPTION_ID
    entry, unbound = law.bound_exception(topology, kinds, authority)
    assert unbound == []
    assert entry is not None
    assert entry["id"] == EXCEPTION_ID
    assert entry["effective_models"] == {
        "consumption_model": topology["consumption"]["model"],
        "deployment_model": topology["deployment"]["model"],
    }
    assert _validate(law, authority, topology, tmp_path) == []
    assert _validate(law, authority, topology, tmp_path, release_version="3.0.0") == []


def test_the_canonical_rc029_evaluator_agrees(authority, topology):
    assert _canonical_findings(authority, topology) == []


def _set(path: str, value: Any) -> Callable[[dict[str, Any]], None]:
    def mutate(topo: dict[str, Any]) -> None:
        *parents, leaf = path.split(".")
        node = topo
        for key in parents:
            node = node[key]
        if value is _DELETE:
            node.pop(leaf)
        else:
            node[leaf] = value

    return mutate


_DELETE = object()

HOSTILE: dict[str, tuple[Callable[[dict[str, Any]], None], str]] = {
    "unknown exception id": (
        _set("product.kind_exception_ref", "l9.product-kind-exception/memory-hosted-service@2"),
        "does not resolve",
    ),
    "foreign product id": (
        _set("product.id", "l9-graphiti-memory:product/another-product"),
        "subject product",
    ),
    "foreign canonical repository": (
        _set("identity.canonical_repository", "Quantum-L9/l9-another-repository"),
        "subject repository",
    ),
    "foreign archetype": (
        _set("product.archetype_ref", "l9.dependency-archetype/library@1"),
        "archetype",
    ),
    "claim on the node kind": (_set("product.kind", "node"), "not bound"),
    "exception models without the claim": (
        _set("product.kind_exception_ref", _DELETE),
        "contradicts the declared ProductKind",
    ),
    "claim with local-composition models": (
        _set("consumption.model", "local_composition"),
        "consumption.model contradicts",
    ),
    "claim with a consumer-bound deployment": (
        _set("deployment.model", "consumer_bound_artifact"),
        "deployment.model contradicts",
    ),
    "remote protocol not declared": (
        _set("consumption.public_entry_modes", ["python_sdk", "cli", "mcp_stdio"]),
        "excepted protocol",
    ),
    "no authentication contract": (
        _set("security.authentication_contract_refs", []),
        "authentication_contract_refs",
    ),
    "no authorization contract": (
        _set("security.authorization_contract_refs", []),
        "authorization_contract_refs",
    ),
    "service_admitted not declared": (
        _set("admission.kind_specific_requirements", ["consumer binding is separate"]),
        "service_admitted",
    ),
    "runtime identity dropped": (
        _set("identity.dimensions.runtime", {"applicable": False}),
        "runtime identity is required",
    ),
    "actor identity dropped": (
        _set("identity.dimensions.actor", {"applicable": False}),
        "identity.dimensions.actor",
    ),
    "constellation identity claimed": (
        _set("identity.dimensions.constellation", {"applicable": True}),
        "constellation",
    ),
    "gate admission acquired": (
        _set("admission.kind_specific_requirements", ["service_admitted", "gate_admitted"]),
        "gate_admitted",
    ),
    "constellation communication required": (
        _set("communication.constellation_boundary_required", True),
        "Gate-routed Constellation communication",
    ),
}


@pytest.mark.parametrize("case", sorted(HOSTILE))
def test_a_hostile_topology_fails_both_validators(case, law, authority, topology, tmp_path):
    mutate, expected = HOSTILE[case]
    hostile = copy.deepcopy(topology)
    mutate(hostile)
    failures = _validate(law, authority, hostile, tmp_path)
    assert any(expected in failure for failure in failures), failures
    # The authority's own evaluator must reject the same topology; the local
    # validator may be stricter, never more permissive.
    assert _canonical_findings(authority, hostile), case


def test_an_unadmitted_exception_binds_nothing(law, authority, kinds, topology):
    drifted = copy.deepcopy(kinds)
    drifted["kind_exceptions"][0]["status"] = "proposed"
    entry, unbound = law.bound_exception(topology, drifted, authority)
    assert entry is None
    assert any("not admitted" in reason for reason in unbound)
    duplicated = copy.deepcopy(kinds)
    duplicated["kind_exceptions"].append(copy.deepcopy(kinds["kind_exceptions"][0]))
    entry, unbound = law.bound_exception(topology, duplicated, authority)
    assert entry is None
    assert unbound


def test_a_retired_registry_entry_unbinds_the_claim(law, authority, kinds, topology, tmp_path):
    shadow = tmp_path / "authority"
    shutil.copytree(authority / "semantics", shadow / "semantics")
    registry_path = shadow / "semantics" / "repository_registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    for entry in registry["repositories"]:
        if entry.get("id") == "l9-graphiti-memory":
            entry["lifecycle"] = "retired"
    registry_path.write_text(yaml.safe_dump(registry, sort_keys=False), encoding="utf-8")
    entry, unbound = law.bound_exception(topology, kinds, shadow)
    assert entry is None
    assert any("registry" in reason for reason in unbound)


@pytest.mark.parametrize(
    ("version", "admitted"),
    [("3.0.0", True), ("3.0.1", True), ("4.0.0", True), ("2.9.9", False), ("2.7.0", False)],
)
def test_the_release_floor_binds_release_admission(
    version, admitted, law, authority, kinds, topology
):
    failures = law.check_release_floor(topology, kinds, authority, version)
    assert (failures == []) is admitted, failures


@pytest.mark.parametrize("version", ["", "3.0", "3.0.0rc1", "v3.0.0", "latest"])
def test_an_unparseable_release_version_fails_closed(version, law, authority, kinds, topology):
    failures = law.check_release_floor(topology, kinds, authority, version)
    assert failures
    assert "cannot be evaluated" in failures[0]


def test_the_manifest_gate_fails_an_unbound_claim(authority, topology, tmp_path):
    generator = _module("generate_product_manifest", ASSURANCE / "generate_product_manifest.py")
    hostile = copy.deepcopy(topology)
    hostile["identity"]["canonical_repository"] = "Quantum-L9/l9-another-repository"
    path = tmp_path / "product-topology.yaml"
    path.write_text(yaml.safe_dump(hostile, sort_keys=False), encoding="utf-8")
    law = generator.Law(authority)
    failing = generator.evaluate_gate(hostile, law, REPO_ROOT, path)
    assert failing["product_kind_exception_absent_or_exactly_bound_and_admitted"]
    bound = generator.evaluate_gate(topology, law, REPO_ROOT, TOPOLOGY)
    assert not any(bound.values()), {k: v for k, v in bound.items() if v}
