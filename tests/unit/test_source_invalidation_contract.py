# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_source_invalidation_contract.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.5.0
#   updated: 2026-10-02

"""ADR-095: the source invalidation request contract fails closed.

Canonical requests carry ``selectors[]`` and ``event_id``; the legacy singular
``selector`` stays an explicit compatibility form of memory-control-plane/v1.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from l9_graphite_memory import cli
from l9_graphite_memory.contracts import EvidenceKind, EvidenceRef, MemoryClass, Provenance
from l9_graphite_memory.contracts.generated_data import (
    GENERATED_DATA_SOURCE,
    SourceInvalidationReceipt,
    SourceInvalidationRequest,
    SourceInvalidationStatus,
    source_selectors_for_record,
)
from l9_graphite_memory.contracts.memory import MemoryRecord
from l9_graphite_memory.version import CONTROL_PLANE_CONTRACT_VERSION

PATH = "src/l9_graphite_memory/services"


def _canonical(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "event_id": "invalidation-001",
        "event_type": "repository_path_changed",
        "repository": "Quantum-L9/example",
        "from_sha": "a" * 40,
        "to_sha": "b" * 40,
        "selectors": [{"selector_type": "relevant_path_changed", "selector_value": PATH}],
        "delete_memory": False,
    }
    request.update(overrides)
    return request


def _legacy(**overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "event_type": "repository_path_changed",
        "selector": {"condition_type": "relevant_path_changed", "selector": PATH},
    }
    request.update(overrides)
    return request


def test_control_plane_contract_version_is_unchanged() -> None:
    assert CONTROL_PLANE_CONTRACT_VERSION == "memory-control-plane/v1"


def test_canonical_selectors_are_the_canonical_form() -> None:
    request = SourceInvalidationRequest.model_validate(_canonical())
    assert request.compatibility_form == "canonical"
    (selector,) = request.normalized_selectors()
    assert (selector.selector_type, selector.selector_value) == ("relevant_path_changed", PATH)
    assert selector.selector_id.startswith("selector-")
    assert request.operation_id() == "invalidation-001"


def test_legacy_singular_selector_normalizes_to_one_element_selectors() -> None:
    request = SourceInvalidationRequest.model_validate(_legacy())
    assert request.compatibility_form == "legacy_selector"
    (selector,) = request.normalized_selectors()
    assert (selector.selector_type, selector.selector_value) == ("relevant_path_changed", PATH)
    assert request.repository is None and request.event_id is None


@pytest.mark.parametrize(
    "payload",
    [
        _canonical(unexpected="field"),
        _canonical(selectors=[{"selector_type": "t", "selector_value": "v", "extra": 1}]),
        _legacy(selector={"condition_type": "t", "selector": "v", "free_text": "x"}),
    ],
    ids=["request", "canonical-selector", "legacy-selector"],
)
def test_unknown_fields_fail_closed(payload: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SourceInvalidationRequest.model_validate(payload)


def test_selector_and_selectors_together_fail() -> None:
    with pytest.raises(ValidationError, match="mutually exclusive"):
        SourceInvalidationRequest.model_validate(
            _canonical(selector={"selector_type": "t", "selector_value": "v"})
        )


@pytest.mark.parametrize("selectors", [None, []], ids=["absent", "empty"])
def test_missing_selectors_fail(selectors: list[Any] | None) -> None:
    payload = _canonical()
    if selectors is None:
        payload.pop("selectors")
    else:
        payload["selectors"] = selectors
    with pytest.raises(ValidationError, match="structured selectors"):
        SourceInvalidationRequest.model_validate(payload)


@pytest.mark.parametrize("field", ["delete_memory", "create_replacement_record"])
def test_deletion_and_replacement_fail(field: str) -> None:
    with pytest.raises(ValidationError):
        SourceInvalidationRequest.model_validate(_canonical(**{field: True}))


def test_both_spellings_of_one_selector_value_fail() -> None:
    selector = {"selector_type": "t", "condition_type": "t", "selector_value": "v"}
    with pytest.raises(ValidationError, match="exactly one"):
        SourceInvalidationRequest.model_validate(_canonical(selectors=[selector]))


@pytest.mark.parametrize("missing", ["event_id", "repository"])
def test_canonical_form_requires_identity_and_repository(missing: str) -> None:
    payload = _canonical()
    payload.pop(missing)
    with pytest.raises(ValidationError, match=missing):
        SourceInvalidationRequest.model_validate(payload)


def test_unsupported_schema_major_fails() -> None:
    with pytest.raises(ValidationError, match="schema major"):
        SourceInvalidationRequest.model_validate(_canonical(schema_version="2.0.0"))


def test_legacy_operation_identity_is_derived_from_the_normalized_body() -> None:
    first = SourceInvalidationRequest.model_validate(_legacy())
    again = SourceInvalidationRequest.model_validate(_legacy())
    other = SourceInvalidationRequest.model_validate(
        _legacy(selector={"condition_type": "relevant_path_changed", "selector": "docs"})
    )
    assert first.operation_id() == again.operation_id()
    assert first.operation_id().startswith("legacy-invalidation-")
    # Same event type, different body: never the same operation.
    assert first.operation_id() != other.operation_id()
    # The canonical spelling of the same selector is the same body.
    spelled = SourceInvalidationRequest.model_validate(
        _legacy(selector={"selector_type": "relevant_path_changed", "selector_value": PATH})
    )
    assert spelled.operation_id() == first.operation_id()


def test_request_digest_ignores_selector_order_and_envelope() -> None:
    selectors = [
        {"selector_type": "relevant_path_changed", "selector_value": "a"},
        {"selector_type": "relevant_path_changed", "selector_value": "b"},
    ]
    forward = SourceInvalidationRequest.model_validate(_canonical(selectors=selectors))
    reverse = SourceInvalidationRequest.model_validate(
        _canonical(selectors=list(reversed(selectors)), metadata={"producer": "x"})
    )
    changed = SourceInvalidationRequest.model_validate(_canonical(to_sha="c" * 40))
    assert forward.request_digest() == reverse.request_digest()
    assert forward.request_digest() != changed.request_digest()


def test_receipt_status_domain_and_deletion_are_fixed() -> None:
    assert {item.value for item in SourceInvalidationStatus} == {"applied", "rejected"}
    receipt = SourceInvalidationReceipt(status="applied", event_type="x")
    assert receipt.deleted is False
    with pytest.raises(ValidationError):
        SourceInvalidationReceipt(status="applied", event_type="x", deleted=True)


def _record(metadata: dict[str, Any], *, source: str = GENERATED_DATA_SOURCE) -> MemoryRecord:
    return MemoryRecord(
        tenant_id="tenant-a",
        namespace="repo-a",
        memory_class=MemoryClass.SEMANTIC,
        content="statement mentioning src/other/path that must never become a selector",
        provenance=Provenance(source=source),
        evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
        metadata=metadata,
        normalized_digest="0" * 64,
        original_digest="0" * 64,
        idempotency_key=f"k-{uuid4()}",
        created_by="tester",
    )


def _metadata(conditions: list[Any]) -> dict[str, Any]:
    return {
        "generated_data_kind": "MemoryCandidate",
        "repository": "Quantum-L9/example",
        "invalidation_conditions": conditions,
    }


def test_selector_mapping_reads_structured_metadata_only() -> None:
    record = _record(_metadata([{"condition_type": "relevant_path_changed", "selector": PATH}]))
    (selector,) = source_selectors_for_record(record)
    assert (selector.repository, selector.selector_type, selector.selector_value) == (
        "Quantum-L9/example",
        "relevant_path_changed",
        PATH,
    )
    assert selector.record_id == record.record_id and selector.active
    assert source_selectors_for_record(record) == (selector,)  # deterministic


@pytest.mark.parametrize(
    "conditions",
    [
        [],
        ["src/l9_graphite_memory/services changed"],
        [{"condition_type": "relevant_path_changed"}],
        [{"condition_type": "relevant_path_changed", "selector": PATH, "note": "x"}],
        [
            {"condition_type": "relevant_path_changed", "selector": PATH},
            {"condition_type": "relevant_path_changed", "selector": ""},
        ],
    ],
    ids=["empty", "prose", "missing-value", "extra-key", "one-unmappable"],
)
def test_selector_mapping_is_lossless_or_absent(conditions: list[Any]) -> None:
    assert source_selectors_for_record(_record(_metadata(conditions))) == ()


def test_selector_mapping_ignores_non_generated_records() -> None:
    metadata = _metadata([{"condition_type": "relevant_path_changed", "selector": PATH}])
    assert source_selectors_for_record(_record(metadata, source="agent")) == ()


# -- CLI machine protocol -------------------------------------------------------------


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("L9_MEMORY_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("L9_MEMORY_STATE_DIR", str(tmp_path / "state"))
    monkeypatch.setenv("L9_MEMORY_NAMESPACE", "repo-a")
    monkeypatch.setenv("L9_MEMORY_JSON_LOGS", "0")
    for name in ("L9_MEMORY_CONFIG", "GRAPHITI_GROUP_ID", "CURSOR_CONVERSATION_ID"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _cli(cli_env: Path, capsys, command: str, payload: dict[str, Any]) -> tuple[int, str, str]:
    path = cli_env / f"{uuid4().hex}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    code = cli.main([command, "--file", str(path)])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_cli_invalidate_source_protocol(cli_env, capsys) -> None:
    fixtures = Path(__file__).resolve().parents[2] / "deployment" / "generated-data" / "fixtures"
    candidate = json.loads((fixtures / "governed-candidate.json").read_text(encoding="utf-8"))
    candidate["source"]["visibility"] = "namespace_local"
    candidate["source"]["namespace"] = "repo-a"
    code, out, _ = _cli(cli_env, capsys, "ingest-governed-candidate", candidate)
    assert code == 0
    record_id = json.loads(out)["record_id"]
    request = _canonical(
        repository=candidate["source"]["repository"],
        selectors=[{"condition_type": "relevant_path_changed", "selector": PATH}],
    )

    code, out, _ = _cli(cli_env, capsys, "invalidate-source", request)
    applied = json.loads(out)
    assert code == 0
    assert applied["status"] == "applied" and applied["deleted"] is False
    assert (applied["matched"], applied["transitioned"]) == (1, 1)
    assert applied["record_ids"] == [record_id]

    code, out, _ = _cli(cli_env, capsys, "invalidate-source", request)
    assert code == 0 and json.loads(out) == applied

    code, out, _ = _cli(cli_env, capsys, "invalidate-source", {**request, "to_sha": "c" * 40})
    assert code == 7 and json.loads(out)["status"] == "rejected"

    code, out, err = _cli(cli_env, capsys, "invalidate-source", {**request, "surprise": 1})
    assert code == 1 and out == "" and "ValidationError" in err
