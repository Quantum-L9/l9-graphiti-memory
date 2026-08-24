# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/topology_publication/test_plan_parser.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Versioned publication-plan parsing: exact contract, fail-closed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from l9_graphite_memory.ingestion import (
    TopologyPlanError,
    load_publication_plan,
    load_verified_bundle,
)
from tests.unit.topology_publication.conftest import (
    make_candidate,
    make_plan_bundle,
)


def _load(root: Path):
    return load_publication_plan(load_verified_bundle(root))


def test_well_formed_plan_parses_with_canonical_intent_validation(
    tmp_path: Path,
) -> None:
    root = make_plan_bundle(
        tmp_path / "plan", [make_candidate(candidate_id="c-1", status="eligible")]
    )
    plan = _load(root)
    assert plan.plan_version == "1.0.0"
    assert plan.candidates[0].memory_intent.operation == "memory.ingest"
    assert plan.candidates[0].memory_intent.request.namespace.startswith("l9.constellation/")


def test_unsupported_plan_version_is_rejected(tmp_path: Path) -> None:
    root = make_plan_bundle(
        tmp_path / "plan",
        [make_candidate(candidate_id="c-1", status="eligible")],
        plan_version="2.0.0",
    )
    with pytest.raises(TopologyPlanError, match="unsupported plan version"):
        _load(root)


def test_wrong_plan_type_is_rejected(tmp_path: Path) -> None:
    root = make_plan_bundle(
        tmp_path / "plan",
        [make_candidate(candidate_id="c-1", status="eligible")],
        plan_type="l9.some-other-plan",
    )
    with pytest.raises(TopologyPlanError, match="publication plan is invalid"):
        _load(root)


def test_duplicate_candidate_ids_reject_the_plan(tmp_path: Path) -> None:
    root = make_plan_bundle(
        tmp_path / "plan",
        [
            make_candidate(candidate_id="c-1", status="eligible"),
            make_candidate(candidate_id="c-1", status="held"),
        ],
    )
    with pytest.raises(TopologyPlanError, match="duplicate candidate_id"):
        _load(root)


def test_unknown_plan_fields_are_rejected(tmp_path: Path) -> None:
    root = make_plan_bundle(
        tmp_path / "plan", [make_candidate(candidate_id="c-1", status="eligible")]
    )
    plan_path = root / "publication-plan.json"
    document = json.loads(plan_path.read_text(encoding="utf-8"))
    document["surprise_field"] = True
    content = json.dumps(document, sort_keys=True).encode("utf-8") + b"\n"
    plan_path.write_bytes(content)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    import hashlib

    manifest["files"][0]["content_hash"] = "sha256:" + hashlib.sha256(content).hexdigest()
    manifest["files"][0]["size_bytes"] = len(content)
    (root / "manifest.json").write_text(json.dumps(manifest, sort_keys=True) + "\n")
    with pytest.raises(TopologyPlanError, match="publication plan is invalid"):
        _load(root)


def test_invalid_embedded_memory_intent_rejects_the_plan(tmp_path: Path) -> None:
    candidate = make_candidate(candidate_id="c-1", status="eligible")
    candidate["memory_intent"]["request"]["namespace"] = ""
    root = make_plan_bundle(tmp_path / "plan", [candidate])
    with pytest.raises(TopologyPlanError, match="publication plan is invalid"):
        _load(root)


def test_unbundled_plan_file_is_not_accepted(tmp_path: Path) -> None:
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "publication-plan.json").write_text("{}")
    with pytest.raises(TopologyPlanError, match="manifest.json"):
        load_verified_bundle(loose)


def test_manifest_plan_id_mismatch_is_rejected(tmp_path: Path) -> None:
    root = make_plan_bundle(
        tmp_path / "plan", [make_candidate(candidate_id="c-1", status="eligible")]
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["packet_id"] = "publication-plan:" + "9" * 64
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    with pytest.raises(TopologyPlanError, match="does not match plan_id"):
        _load(root)


def test_manifest_semantic_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    root = make_plan_bundle(
        tmp_path / "plan", [make_candidate(candidate_id="c-1", status="eligible")]
    )
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["semantic_hash"] = "sha256:" + "9" * 64
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
    with pytest.raises(TopologyPlanError, match="semantic_hash"):
        _load(root)
