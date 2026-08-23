# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/topology_publication/test_locator_future_conformance.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-08-23

"""Forward conformance: topology intents carrying structured source locators.

The bound producer revision does not emit ``source_locator`` yet (pinned in
the E2E suite). These fixtures prove the boundary is ready the day it does:
each binary locator kind arrives inside an otherwise ordinary topology
publication intent, validates through the canonical contract, survives the
whole adapter path, and reads back from the canonical store exactly as sent —
with no fabricated line coordinates anywhere.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from l9_graphite_memory.adapters import NullProjection, SQLiteRecordStore
from l9_graphite_memory.ingestion import (
    execute_topology_publication,
    load_publication_plan,
    load_verified_bundle,
)
from l9_graphite_memory.services import MemoryService
from tests.unit.topology_publication.conftest import (
    EVIDENCE_IDS,
    make_candidate,
    make_plan_bundle,
    make_topology_bundle,
)

FUTURE_LOCATORS: dict[str, dict[str, Any]] = {
    "pdf": {"kind": "pdf", "page_number": 14, "block_index": 2},
    "docx": {"kind": "docx", "block_index": 31, "block_kind": "heading"},
    "pptx": {"kind": "pptx", "slide_number": 5, "shape_index": 0},
    "spreadsheet": {"kind": "spreadsheet", "sheet": "Inventory", "cell_or_range": "A2:C40"},
    "notebook": {"kind": "notebook", "cell_index": 12, "cell_type": "code"},
}


@pytest.mark.parametrize("kind", sorted(FUTURE_LOCATORS))
def test_locator_bearing_topology_intent_roundtrips_canonically(
    tmp_path: Path, topology_principal, kind: str
) -> None:
    locator = FUTURE_LOCATORS[kind]
    candidate = make_candidate(
        candidate_id=f"locator-{kind}",
        status="eligible",
        evidence_ids=(EVIDENCE_IDS[0],),
    )
    request = candidate["memory_intent"]["request"]
    request["evidence"] = [
        {
            "kind": "source_excerpt",
            "description": f"evidence anchored by a {kind} locator",
            "source_id": EVIDENCE_IDS[0],
            "source_locator": locator,
            "observed_at": "2026-03-01T00:00:00Z",
        }
    ]
    request["provenance"]["source_locator"] = locator
    plan_root = make_plan_bundle(tmp_path / "plan", [candidate])
    topo_root = make_topology_bundle(tmp_path / "topo")
    plan = load_publication_plan(load_verified_bundle(plan_root))
    parsed = plan.candidates[0].memory_intent.request
    assert parsed.provenance.source_locator is not None
    assert parsed.provenance.source_locator.kind == kind
    assert parsed.provenance.source_range is None
    assert parsed.evidence[0].source_range is None

    service = MemoryService(
        SQLiteRecordStore(tmp_path / "canonical.sqlite3"), NullProjection()
    )
    service.initialize()
    receipt = execute_topology_publication(
        plan=plan,
        topology_bundle=load_verified_bundle(topo_root),
        principal=topology_principal,
        memory_service=service,
        mode="apply",
    )
    assert receipt.admitted_count == 1
    record = service.get(topology_principal, receipt.candidate_results[0].memory_record_id)
    stored_provenance = record.provenance.source_locator
    stored_evidence = record.evidence[0].source_locator
    assert stored_provenance is not None
    assert stored_evidence is not None
    assert stored_provenance.model_dump(mode="json") == locator
    assert stored_evidence.model_dump(mode="json") == locator
    assert record.provenance.source_range is None
    assert record.evidence[0].source_range is None


def test_invalid_dual_coordinates_from_topology_are_rejected(tmp_path: Path) -> None:
    from l9_graphite_memory.ingestion import TopologyPlanError

    candidate = make_candidate(candidate_id="dual", status="eligible")
    request = candidate["memory_intent"]["request"]
    request["provenance"]["source_range"] = {"start_line": 1, "end_line": 2}
    request["provenance"]["source_locator"] = FUTURE_LOCATORS["pdf"]
    plan_root = make_plan_bundle(tmp_path / "plan", [candidate])
    with pytest.raises(TopologyPlanError, match="publication plan is invalid"):
        load_publication_plan(load_verified_bundle(plan_root))
