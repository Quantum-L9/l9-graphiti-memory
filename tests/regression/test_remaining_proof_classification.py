# --- L9_META ---
# l9_schema: 1
# repo: Quantum-L9/l9-graphiti-memory
# path: tests/regression/test_remaining_proof_classification.py
# layer: tests
# owner: memory-control-plane
# status: active
# version: 3.0.0
# updated: 2026-11-14
# --- /L9_META ---
"""ADR-105: the reviewed remaining-proof classification has one source of truth.

`release-work/remaining-proof-classification.json` is that source. The table in
`docs/REMAINING_PRODUCTION_PROOF.md` must state the same (item, scope, class)
rows, and the release evidence generator derives each external finding's
`blocks_production_release` and the report's `production_release_status` from
it. Anything the classification does not settle fails closed to
BLOCKED_ON_EXTERNAL_VALIDATION.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR = REPO_ROOT / "tools" / "assurance" / "generate_validation_evidence.py"
DOCUMENT = REPO_ROOT / "docs" / "REMAINING_PRODUCTION_PROOF.md"

# Document wording -> machine class.
DOCUMENT_CLASSES = {
    "CLOSED": "CLOSED",
    "NOT APPLICABLE TO THIS RELEASE": "NOT_APPLICABLE_TO_THIS_RELEASE",
    "OPEN — ACCEPTED RESIDUAL RISK": "OPEN_ACCEPTED_RESIDUAL_RISK",
    "OPEN": "OPEN_RELEASE_DECISION",
}


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("classification_validation_evidence", GENERATOR)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load()
CLASSIFICATION = REPO_ROOT / MODULE.CLASSIFICATION


def _file() -> dict[str, object]:
    data = json.loads(CLASSIFICATION.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _document_rows() -> set[tuple[str, str, str]]:
    text = DOCUMENT.read_text(encoding="utf-8")
    section = text.split("## 3.0.0 classification", 1)[1].split("\n## ", 1)[0]
    rows: set[tuple[str, str, str]] = set()
    for line in section.splitlines():
        if not line.startswith("| RP-0"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        item = re.match(r"RP-\d{3}", cells[0])
        assert item, line
        label = cells[2].strip("*").strip()
        assert label in DOCUMENT_CLASSES, f"unknown class wording {label!r} in {line}"
        rows.add((item.group(0), cells[1], DOCUMENT_CLASSES[label]))
    return rows


def _file_rows() -> set[tuple[str, str, str]]:
    items = _file()["items"]
    assert isinstance(items, list)
    return {(row["item"], row["scope"], row["classification"]) for row in items}


def test_document_table_and_classification_file_agree() -> None:
    document = _document_rows()
    assert document, "no classification rows found in the document"
    assert document == _file_rows()


def test_classification_file_is_for_this_release() -> None:
    from l9_graphite_memory.version import PACKAGE_VERSION

    data = _file()
    assert data["schema"] == MODULE.CLASSIFICATION_SCHEMA
    assert data["release"] == PACKAGE_VERSION == MODULE.RELEASE


def test_every_external_finding_is_mapped() -> None:
    mapping = _file()["external_findings"]
    assert isinstance(mapping, dict)
    assert set(mapping) == {blocker["id"] for blocker in MODULE.EXTERNAL_BLOCKERS}


def test_admissible_status_does_not_claim_validation() -> None:
    status = MODULE.ADMISSIBLE_STATUS
    assert status != MODULE.BLOCKED_STATUS
    for word in ("VALIDATED", "PASS", "PROVEN", "APPROVED", "PRODUCTION"):
        assert word not in status


def test_b001_reason_reflects_the_bound_transport_packet_package() -> None:
    b001 = next(b for b in MODULE.EXTERNAL_BLOCKERS if b["id"] == "B-001")
    assert "unavailable in this pack" not in b001["reason"]
    assert "RP-001" in b001["reason"]


# --- the generator, end to end on a minimal tree ------------------------------


def _tree(tmp_path: Path, *, classification: dict[str, object] | None, version: str) -> Path:
    root = tmp_path / "repo"
    (root / "release-work").mkdir(parents=True)
    (root / "src" / "l9_graphite_memory").mkdir(parents=True)
    (root / "src" / "l9_graphite_memory" / "version.py").write_text(
        f'PACKAGE_VERSION = "{version}"\n', encoding="utf-8"
    )
    if classification is not None:
        (root / MODULE.CLASSIFICATION).write_text(json.dumps(classification), encoding="utf-8")
    return root


def _generate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, root: Path
) -> tuple[dict[str, object], list[dict[str, object]]]:
    # No local checks: this exercises only the external-finding classification.
    monkeypatch.setattr(MODULE, "CHECKS", ())
    evidence = tmp_path / "evidence"
    assert MODULE.generate(root, evidence) == 0
    report = json.loads((evidence / "validation_report.yaml").read_text(encoding="utf-8"))
    findings = [
        json.loads(line)
        for line in (evidence / "validation_findings.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    return report, findings


def test_this_tree_is_admissible_with_every_finding_still_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    (root / "release-work").mkdir(parents=True)
    (root / "src" / "l9_graphite_memory").mkdir(parents=True)
    shutil.copy(CLASSIFICATION, root / MODULE.CLASSIFICATION)
    shutil.copy(REPO_ROOT / MODULE.PACKAGE_VERSION_FILE, root / MODULE.PACKAGE_VERSION_FILE)
    report, findings = _generate(tmp_path, monkeypatch, root)
    assert report["production_release_status"] == MODULE.ADMISSIBLE_STATUS
    assert report["external_findings_blocking"] == 0
    assert [f["finding_id"] for f in findings] == ["B-001", "B-002", "B-003", "B-004", "B-005"]
    for finding in findings:
        assert finding["blocks_production_release"] is False
        assert finding["release_classification"]
        assert finding["impact"] == "production release cannot be claimed from local evidence alone"


def test_missing_classification_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path, classification=None, version=MODULE.RELEASE)
    report, findings = _generate(tmp_path, monkeypatch, root)
    assert report["production_release_status"] == MODULE.BLOCKED_STATUS
    assert all(f["blocks_production_release"] is True for f in findings)


def test_finding_without_a_classification_entry_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _file()
    mapping = dict(data["external_findings"])  # type: ignore[arg-type]
    del mapping["B-003"]
    data["external_findings"] = mapping
    root = _tree(tmp_path, classification=data, version=MODULE.RELEASE)
    report, findings = _generate(tmp_path, monkeypatch, root)
    assert report["production_release_status"] == MODULE.BLOCKED_STATUS
    blocked = {f["finding_id"] for f in findings if f["blocks_production_release"]}
    assert blocked == {"B-003"}


def test_item_without_a_classification_row_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _file()
    data["items"] = [row for row in data["items"] if row["item"] != "RP-008"]  # type: ignore[union-attr]
    root = _tree(tmp_path, classification=data, version=MODULE.RELEASE)
    report, findings = _generate(tmp_path, monkeypatch, root)
    assert report["production_release_status"] == MODULE.BLOCKED_STATUS
    assert {f["finding_id"] for f in findings if f["blocks_production_release"]} == {"B-005"}


def test_unknown_class_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = _file()
    items = [dict(row) for row in data["items"]]  # type: ignore[union-attr]
    for row in items:
        if row["item"] == "RP-004" and row["scope"] == "package":
            row["classification"] = "PROBABLY_FINE"
    data["items"] = items
    root = _tree(tmp_path, classification=data, version=MODULE.RELEASE)
    report, findings = _generate(tmp_path, monkeypatch, root)
    assert report["production_release_status"] == MODULE.BLOCKED_STATUS
    assert {f["finding_id"] for f in findings if f["blocks_production_release"]} == {"B-002"}


def test_release_decision_class_blocks_a_finding_mapped_to_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = _file()
    data["external_findings"] = {**data["external_findings"], "B-004": ["RP-009"]}  # type: ignore[dict-item]
    root = _tree(tmp_path, classification=data, version=MODULE.RELEASE)
    report, _ = _generate(tmp_path, monkeypatch, root)
    assert report["production_release_status"] == MODULE.BLOCKED_STATUS


def test_version_mismatch_with_package_version_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path, classification=_file(), version="3.0.1")
    report, findings = _generate(tmp_path, monkeypatch, root)
    assert report["production_release_status"] == MODULE.BLOCKED_STATUS
    assert all(f["blocks_production_release"] is True for f in findings)
    assert any("PACKAGE_VERSION" in p for p in report["release_classification"]["problems"])


def test_classification_for_another_release_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = {**_file(), "release": "2.6.0"}
    root = _tree(tmp_path, classification=data, version=MODULE.RELEASE)
    report, findings = _generate(tmp_path, monkeypatch, root)
    assert report["production_release_status"] == MODULE.BLOCKED_STATUS
    assert all(f["blocks_production_release"] is True for f in findings)


def test_unparseable_classification_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _tree(tmp_path, classification=None, version=MODULE.RELEASE)
    (root / MODULE.CLASSIFICATION).write_text("{not json", encoding="utf-8")
    report, _ = _generate(tmp_path, monkeypatch, root)
    assert report["production_release_status"] == MODULE.BLOCKED_STATUS
