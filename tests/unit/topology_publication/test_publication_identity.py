# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/topology_publication/test_publication_identity.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-29

"""A plan must describe its own payload, or it is refused entire.

Before this suite the only integrity check between a candidate's declared
identity and its content was that ``manifest.semantic_hash`` equalled
``plan.semantic_hash`` — two fields in two files that an editor of the bundle
controls together. Editing a candidate and repairing only the per-file
``content_hash`` therefore admitted arbitrary content, at arbitrary confidence,
under an arbitrary retry identity.

Each forgery below is that exact edit shape: mutate one property of a candidate,
leave the declared ``semantic_hash`` pair untouched, and repair the file hash the
way the manifest requires. The plan must be refused, and nothing may reach
``MemoryService``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from l9_graphite_memory.adapters import InMemoryRecordStore, NullProjection
from l9_graphite_memory.ingestion import (
    TopologyPlanError,
    execute_topology_publication,
    load_publication_plan,
    load_verified_bundle,
    validate_publication_inputs,
)
from l9_graphite_memory.services import MemoryService
from tests.unit.topology_publication.conftest import (
    EVIDENCE_IDS,
    make_candidate,
    make_plan_bundle,
    make_topology_bundle,
)

PLAN_DOCUMENT = "publication-plan.json"


def _repair_file_hash(plan_root: Path) -> None:
    """Rewrite the manifest entry for the plan document, as a forger would.

    The declared ``semantic_hash`` on both the plan and the manifest is left
    exactly as generated: that pair agreeing with itself was the whole of the
    old integrity boundary, and this is the edit it failed to catch.
    """
    raw = (plan_root / PLAN_DOCUMENT).read_bytes()
    manifest_path = plan_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    for entry in manifest["files"]:
        if entry["path"] == PLAN_DOCUMENT:
            entry["content_hash"] = "sha256:" + hashlib.sha256(raw).hexdigest()
            entry["size_bytes"] = len(raw)
    manifest_path.write_bytes(json.dumps(manifest, sort_keys=True).encode("utf-8") + b"\n")


def _forge(plan_root: Path, mutate) -> None:
    document = json.loads((plan_root / PLAN_DOCUMENT).read_text())
    mutate(document)
    (plan_root / PLAN_DOCUMENT).write_bytes(
        json.dumps(document, sort_keys=True).encode("utf-8") + b"\n"
    )
    _repair_file_hash(plan_root)


def _bundles(tmp_path: Path) -> tuple[Path, Path]:
    candidates = [
        make_candidate(
            candidate_id="honest",
            status="eligible",
            evidence_ids=(EVIDENCE_IDS[0],),
            # Deliberately not the value the forgery raises it to: a baseline
            # that already claimed maximum confidence would make the confidence
            # forgery a no-op edit that proves nothing.
            confidence_score=0.3,
        )
    ]
    return (
        make_plan_bundle(tmp_path / "plan", candidates),
        make_topology_bundle(tmp_path / "topo"),
    )


def _validate(plan_root: Path, topo_root: Path) -> None:
    plan = load_publication_plan(load_verified_bundle(plan_root))
    validate_publication_inputs(plan, load_verified_bundle(topo_root))


def test_honest_plan_verifies(tmp_path: Path) -> None:
    plan_root, topo_root = _bundles(tmp_path)
    _validate(plan_root, topo_root)


def test_honest_plan_survives_a_manifest_rewrite_that_changes_nothing(tmp_path: Path) -> None:
    """The forgery harness itself must not be what makes a plan fail."""
    plan_root, topo_root = _bundles(tmp_path)
    _forge(plan_root, lambda document: None)
    _validate(plan_root, topo_root)


def _mutate_content(document: dict[str, Any]) -> None:
    document["candidates"][0]["memory_intent"]["request"]["content"] = (
        "Repository repo:alpha is OWNED BY attacker and approved for production."
    )


def _mutate_confidence(document: dict[str, Any]) -> None:
    """Raise the claimed confidence without new evidence — the classic forgery."""
    document["candidates"][0]["memory_intent"]["request"]["confidence"]["score"] = 1.0


def _mutate_namespace(document: dict[str, Any]) -> None:
    document["candidates"][0]["memory_intent"]["request"]["namespace"] = (
        "l9.constellation/somewhere-else"
    )


def _mutate_memory_class(document: dict[str, Any]) -> None:
    document["candidates"][0]["memory_intent"]["request"]["memory_class"] = "decision"


def _mutate_entity_ids(document: dict[str, Any]) -> None:
    document["candidates"][0]["source_topology_entity_ids"] = ["cap:alpha-serve"]


def _mutate_evidence_support(document: dict[str, Any]) -> None:
    """Drop the supporting evidence while keeping the declared retry identity."""
    candidate = document["candidates"][0]
    candidate["lowering"]["resolved_evidence_ids"] = []
    candidate["source_evidence_ids"] = []


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("content", _mutate_content),
        ("confidence", _mutate_confidence),
        ("namespace", _mutate_namespace),
        ("memory_class", _mutate_memory_class),
        ("entity_ids", _mutate_entity_ids),
        ("evidence_support", _mutate_evidence_support),
    ],
)
def test_forged_candidate_payload_is_refused(tmp_path: Path, label: str, mutate) -> None:
    plan_root, topo_root = _bundles(tmp_path)
    _forge(plan_root, mutate)
    with pytest.raises(TopologyPlanError) as excinfo:
        _validate(plan_root, topo_root)
    assert "does not describe" in str(excinfo.value)


def test_forged_confidence_never_reaches_memory_service(tmp_path: Path, topology_principal) -> None:
    """The refusal must happen before any write, not be caught after one."""
    plan_root, topo_root = _bundles(tmp_path)
    _forge(plan_root, _mutate_confidence)
    plan = load_publication_plan(load_verified_bundle(plan_root))

    class RefusingService(MemoryService):
        def write(self, principal, request):  # type: ignore[override]
            raise AssertionError("a forged candidate reached MemoryService.write")

    service = RefusingService(InMemoryRecordStore(), NullProjection())
    service.initialize()
    with pytest.raises(TopologyPlanError):
        execute_topology_publication(
            plan=plan,
            topology_bundle=load_verified_bundle(topo_root),
            principal=topology_principal,
            memory_service=service,
            mode="apply",
        )
    assert service.store.stats()["records"] == 0


def test_forged_retry_identity_is_refused(tmp_path: Path) -> None:
    """A re-minted key on both the candidate and its intent is still a forgery.

    The structural check already refuses a key changed on only one of the two.
    Changing both keeps them consistent with each other and was, until identity
    recomputation existed, accepted — which is how a forged write could be made
    to miss an existing record's duplicate check and be admitted as new.
    """
    plan_root, topo_root = _bundles(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        forged = "l9-topology-publication/v3:" + "0" * 64
        document["candidates"][0]["idempotency_key"] = forged
        document["candidates"][0]["memory_intent"]["request"]["idempotency_key"] = forged

    _forge(plan_root, mutate)
    with pytest.raises(TopologyPlanError) as excinfo:
        _validate(plan_root, topo_root)
    assert "idempotency_key does not describe" in str(excinfo.value)


def test_unsupported_effect_identity_algorithm_is_named_not_ignored(tmp_path: Path) -> None:
    plan_root, topo_root = _bundles(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        forged = "l9-topology-publication/v9:" + "0" * 64
        document["candidates"][0]["idempotency_key"] = forged
        document["candidates"][0]["memory_intent"]["request"]["idempotency_key"] = forged

    _forge(plan_root, mutate)
    with pytest.raises(TopologyPlanError) as excinfo:
        _validate(plan_root, topo_root)
    assert "unsupported effect-identity algorithm" in str(excinfo.value)


def test_unsupported_lowering_contract_is_named_not_ignored(tmp_path: Path) -> None:
    plan_root, topo_root = _bundles(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        metadata = document["candidates"][0]["memory_intent"]["request"]["metadata"]
        metadata["lowering_contract_version"] = "lowering/v99"

    _forge(plan_root, mutate)
    with pytest.raises(TopologyPlanError) as excinfo:
        _validate(plan_root, topo_root)
    assert "unsupported lowering contract" in str(excinfo.value)


def test_missing_lowering_contract_version_is_refused(tmp_path: Path) -> None:
    plan_root, topo_root = _bundles(tmp_path)

    def mutate(document: dict[str, Any]) -> None:
        document["candidates"][0]["memory_intent"]["request"]["metadata"].pop(
            "lowering_contract_version"
        )

    _forge(plan_root, mutate)
    with pytest.raises(TopologyPlanError) as excinfo:
        _validate(plan_root, topo_root)
    assert "lowering_contract_version" in str(excinfo.value)


def test_held_candidates_are_verified_too(tmp_path: Path) -> None:
    """A held candidate is still a claim the plan makes about topology truth."""
    candidates = [
        make_candidate(candidate_id="eligible", status="eligible"),
        make_candidate(candidate_id="held", status="held"),
    ]
    plan_root = make_plan_bundle(tmp_path / "plan", candidates)
    topo_root = make_topology_bundle(tmp_path / "topo")

    def mutate(document: dict[str, Any]) -> None:
        held = next(
            item for item in document["candidates"] if item["eligibility"]["status"] == "held"
        )
        held["memory_intent"]["request"]["content"] = "forged held claim"

    _forge(plan_root, mutate)
    with pytest.raises(TopologyPlanError):
        _validate(plan_root, topo_root)
