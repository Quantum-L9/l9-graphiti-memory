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
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
TOPOLOGY = REPO_ROOT / "product-topology.yaml"
DECISION = REPO_ROOT / "docs" / "adr" / "ADR-085-product-topology-and-release-governance.md"
BINDING = REPO_ROOT / "release-work" / "product-release-binding.yaml"


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
