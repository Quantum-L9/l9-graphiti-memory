# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/topology_publication/test_plan_integrity.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Bundle integrity and topology source binding, fail-closed."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from l9_graphite_memory.ingestion import (
    TopologyPlanError,
    load_publication_plan,
    load_verified_bundle,
    validate_topology_binding,
)
from tests.unit.topology_publication.conftest import (
    EVIDENCE_IDS,
    make_candidate,
    make_plan_bundle,
    make_topology_bundle,
)


def _bind(plan_root: Path, topo_root: Path) -> None:
    plan = load_publication_plan(load_verified_bundle(plan_root))
    validate_topology_binding(plan, load_verified_bundle(topo_root))


def test_intact_bundles_bind(tmp_path: Path) -> None:
    plan_root = make_plan_bundle(
        tmp_path / "plan",
        [
            make_candidate(
                candidate_id="c-1",
                status="eligible",
                evidence_ids=(EVIDENCE_IDS[0],),
            )
        ],
    )
    topo_root = make_topology_bundle(tmp_path / "topo")
    _bind(plan_root, topo_root)


def test_tampered_bundle_file_fails_integrity(tmp_path: Path) -> None:
    topo_root = make_topology_bundle(tmp_path / "topo")
    payload = topo_root / "payload" / "evidence.json"
    payload.write_text(payload.read_text(encoding="utf-8").replace("alpha", "forged"))
    with pytest.raises(TopologyPlanError, match="integrity verification"):
        load_verified_bundle(topo_root)


def test_size_mismatch_fails_integrity(tmp_path: Path) -> None:
    topo_root = make_topology_bundle(tmp_path / "topo")
    manifest_path = topo_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["size_bytes"] += 1
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    with pytest.raises(TopologyPlanError, match="integrity verification|size mismatch"):
        load_verified_bundle(topo_root)


def test_manifest_path_traversal_is_rejected(tmp_path: Path) -> None:
    topo_root = make_topology_bundle(tmp_path / "topo")
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    manifest_path = topo_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = "../outside.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    with pytest.raises(TopologyPlanError, match="escapes the bundle root"):
        load_verified_bundle(topo_root)


def test_symlink_escaping_the_bundle_root_is_rejected(tmp_path: Path) -> None:
    topo_root = make_topology_bundle(tmp_path / "topo")
    secret = tmp_path / "secret.json"
    secret.write_text("{}")
    target = topo_root / "payload" / "evidence.json"
    target.unlink()
    os.symlink(secret, target)
    with pytest.raises(TopologyPlanError, match="outside the bundle root|integrity"):
        load_verified_bundle(topo_root)


def test_forged_topology_packet_id_is_rejected(tmp_path: Path) -> None:
    plan_root = make_plan_bundle(
        tmp_path / "plan",
        [make_candidate(candidate_id="c-1", status="eligible")],
        source_packet_id="packet:" + "9" * 64,
        source_semantic_hash="sha256:" + "9" * 64,
    )
    topo_root = make_topology_bundle(tmp_path / "topo")
    with pytest.raises(TopologyPlanError, match="cites topology packet"):
        _bind(plan_root, topo_root)


def test_forged_topology_semantic_hash_is_rejected(tmp_path: Path) -> None:
    plan_root = make_plan_bundle(
        tmp_path / "plan",
        [make_candidate(candidate_id="c-1", status="eligible")],
        source_semantic_hash="sha256:" + "9" * 64,
    )
    topo_root = make_topology_bundle(tmp_path / "topo")
    with pytest.raises(TopologyPlanError, match="semantic_hash"):
        _bind(plan_root, topo_root)


def test_unresolvable_entity_id_is_rejected(tmp_path: Path) -> None:
    plan_root = make_plan_bundle(
        tmp_path / "plan",
        [
            make_candidate(
                candidate_id="c-1",
                status="eligible",
                entity_ids=("repo:not-in-the-packet",),
            )
        ],
    )
    topo_root = make_topology_bundle(tmp_path / "topo")
    with pytest.raises(TopologyPlanError, match="does not resolve"):
        _bind(plan_root, topo_root)


def test_unresolvable_evidence_id_is_rejected(tmp_path: Path) -> None:
    plan_root = make_plan_bundle(
        tmp_path / "plan",
        [
            make_candidate(
                candidate_id="c-1",
                status="eligible",
                evidence_ids=("evidence:not-in-the-packet",),
            )
        ],
    )
    topo_root = make_topology_bundle(tmp_path / "topo")
    with pytest.raises(TopologyPlanError, match="cites topology evidence"):
        _bind(plan_root, topo_root)


def test_unbound_repository_model_packet_is_rejected(tmp_path: Path) -> None:
    plan_root = make_plan_bundle(
        tmp_path / "plan",
        [
            make_candidate(
                candidate_id="c-1",
                status="eligible",
                rmp_ids=("packet:" + "b" * 64,),
            )
        ],
    )
    topo_root = make_topology_bundle(tmp_path / "topo")
    with pytest.raises(TopologyPlanError, match="not a bound input"):
        _bind(plan_root, topo_root)


def test_missing_packet_document_is_rejected(tmp_path: Path) -> None:
    topo_root = make_topology_bundle(tmp_path / "topo")
    manifest_path = topo_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = [
        entry for entry in manifest["files"] if entry["path"] != "packet.json"
    ]
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    plan_root = make_plan_bundle(
        tmp_path / "plan", [make_candidate(candidate_id="c-1", status="eligible")]
    )
    with pytest.raises(TopologyPlanError, match="packet.json"):
        _bind(plan_root, topo_root)


def test_bundle_inputs_are_never_modified(tmp_path: Path) -> None:
    plan_root = make_plan_bundle(
        tmp_path / "plan", [make_candidate(candidate_id="c-1", status="eligible")]
    )
    topo_root = make_topology_bundle(tmp_path / "topo")
    before = {
        path: path.read_bytes()
        for path in sorted((*plan_root.rglob("*"), *topo_root.rglob("*")))
        if path.is_file()
    }
    _bind(plan_root, topo_root)
    after = {
        path: path.read_bytes()
        for path in sorted((*plan_root.rglob("*"), *topo_root.rglob("*")))
        if path.is_file()
    }
    assert before == after
