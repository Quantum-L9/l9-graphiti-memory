# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/regression/test_product_release_governance.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-07-22

"""The product-owner decision, the release binding and the topology must agree.

ADR-085 admits one exact ProductTopology digest. A topology edit that is not
re-decided would leave the decision silently stale, and a release binding that
named a different digest would bind release evidence to a topology nobody
admitted. Both are failures here, not review-time judgement.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY = REPO_ROOT / "product-topology.yaml"
DECISION = REPO_ROOT / "docs" / "adr" / "ADR-085-product-topology-and-release-governance.md"
BINDING = REPO_ROOT / "release-work" / "product-release-binding.yaml"
MANIFEST = REPO_ROOT / "release-work" / "product-manifest.json"
GENERATOR = REPO_ROOT / "tools" / "assurance" / "generate_product_manifest.py"
CI = REPO_ROOT / ".github" / "workflows" / "ci.yml"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("generate_product_manifest", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(GENERATOR.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_decision_and_binding_name_the_committed_topology_digest() -> None:
    digest = "sha256:" + hashlib.sha256(TOPOLOGY.read_bytes()).hexdigest()
    binding = yaml.safe_load(BINDING.read_text(encoding="utf-8"))
    decided = re.findall(r"`(sha256:[0-9a-f]{64})`", DECISION.read_text(encoding="utf-8"))
    assert decided == [digest], "ADR-085 is stale: reissue the decision for the new topology digest"
    assert binding["product_topology"]["digest"] == digest
    assert (
        binding["product_topology"]["admission_decision_ref"]
        == DECISION.relative_to(REPO_ROOT).as_posix()
    )
    topology = yaml.safe_load(TOPOLOGY.read_text(encoding="utf-8"))
    assert (
        binding["global_release_contract"]["ref"]
        in topology["distribution"]["release_contract_refs"]
    )
    assert binding["product"]["kind"] == topology["product"]["kind"]
    assert binding["product"]["archetype_ref"] == topology["product"]["archetype_ref"]


def test_binding_never_claims_a_resolved_manifest_without_exact_coordinates() -> None:
    manifest = yaml.safe_load(BINDING.read_text(encoding="utf-8"))["product_manifest"]
    if manifest["status"] == "resolved":
        for key in ("ref", "digest", "compiler_revision", "compiler_profile_digest"):
            assert manifest[key], f"resolved ProductManifest lacks {key}"
        assert re.fullmatch(r"sha256:[0-9a-f]{64}", manifest["digest"])
    else:
        assert manifest["status"] == "unresolved"
        assert manifest["reasons"], "an unresolved ProductManifest must say why"


def test_derived_product_manifest_is_current_and_bound() -> None:
    # The ProductManifest is derived in this repository (ADR-085): it must be
    # the generator's output for the committed topology, carry a digest that
    # recomputes, and agree with the release binding and the CI authority pin.
    # Regenerating it needs the authority checkout; CI runs that --check.
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    generator = _generator()
    assert manifest["schema"] == "l9.product-manifest/v1"
    assert manifest["manifest_digest"] == generator.manifest_digest(manifest)
    assert manifest["source_topology"]["digest"] == _sha256(TOPOLOGY)
    assert manifest["compiler"]["compiler_version"].endswith("@" + _sha256(GENERATOR))
    gate = manifest["resolved_manifest_gate"]
    assert tuple(gate["conditions"]) == tuple(sorted(generator.GATE))
    failing = sorted(name for name, c in gate["conditions"].items() if not c["holds"])
    assert sorted(item["condition"] for item in manifest["unresolved"]) == failing
    assert gate["result"] == ("fail" if failing else "pass")

    binding = yaml.safe_load(BINDING.read_text(encoding="utf-8"))
    bound = binding["product_manifest"]
    assert bound["ref"] == MANIFEST.relative_to(REPO_ROOT).as_posix()
    assert bound["digest"] == manifest["manifest_digest"]
    assert bound["compiler_revision"] == _sha256(GENERATOR)
    assert bound["compiler_profile_digest"] == manifest["compiler"]["profile_digest"]
    assert bound["resolved_manifest_gate"] == gate["result"]
    assert bound["status"] == ("resolved" if gate["result"] == "pass" else "unresolved")
    revision = binding["authority"]["revision"]
    assert manifest["authority"]["revision"] == revision
    assert f"ref: {revision}" in CI.read_text(encoding="utf-8")
