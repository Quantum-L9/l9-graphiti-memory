# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_operation_identity.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-08-20

"""SP-04: retry identity is explicit; semantic content never governs admission."""

from __future__ import annotations

import pytest

from l9_graphite_memory.contracts import (
    EvidenceKind,
    EvidenceRef,
    MemoryClass,
    MemoryWriteRequest,
    Provenance,
    WriteStatus,
)

CONTENT = "the deployment pipeline runs on ubuntu-latest"


def _request(*, idempotency_key: str | None = None, source_id: str) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        namespace="repo-a",
        memory_class=MemoryClass.OBSERVATION,
        content=CONTENT,
        provenance=Provenance(
            source="test-observer",
            source_id=source_id,
            extraction_method="operation-identity-test/v1",
        ),
        evidence=(
            EvidenceRef(
                kind=EvidenceKind.OBSERVATION,
                description="observed during a test run",
                source_id=source_id,
            ),
        ),
        idempotency_key=idempotency_key,
    )


@pytest.fixture(params=["memory_service", "sqlite_service"])
def service(request):
    return request.getfixturevalue(request.param)


def test_retry_of_the_same_operation_dedupes(service, principal) -> None:
    """Same explicit operation identity: the second call is a retry."""

    first = service.write(principal, _request(idempotency_key="op-1", source_id="a"))
    second = service.write(principal, _request(idempotency_key="op-1", source_id="a"))

    assert first.status is WriteStatus.ADMITTED
    assert second.status is WriteStatus.DUPLICATE
    assert second.record_id == first.record_id
    assert first.idempotency_key == second.idempotency_key == "op-1"
    assert first.idempotency_key_supplied is True


def test_identical_content_under_distinct_operations_is_admitted_twice(service, principal) -> None:
    """Same content, different operations: both are admitted independently."""

    first = service.write(principal, _request(idempotency_key="op-a", source_id="a"))
    second = service.write(principal, _request(idempotency_key="op-b", source_id="b"))

    assert first.status is WriteStatus.ADMITTED
    assert second.status is WriteStatus.ADMITTED
    assert first.record_id != second.record_id
    assert first.normalized_digest == second.normalized_digest


def test_identical_content_without_operation_identity_is_admitted_twice(service, principal) -> None:
    """Omitting the key means 'new operation', not 'dedupe me by content'."""

    first = service.write(principal, _request(source_id="a"))
    second = service.write(principal, _request(source_id="b"))

    assert first.status is WriteStatus.ADMITTED
    assert second.status is WriteStatus.ADMITTED
    assert first.record_id != second.record_id
    assert first.idempotency_key != second.idempotency_key
    assert first.idempotency_key_supplied is False


def test_default_operation_identity_is_not_derived_from_content(service, principal) -> None:
    """The semantic digest must not appear in the admission identity."""

    receipt = service.write(principal, _request(source_id="a"))

    assert receipt.normalized_digest not in receipt.idempotency_key
    assert receipt.original_digest not in receipt.idempotency_key
    assert receipt.idempotency_key.startswith("operation:repo-a:")


def test_semantic_digest_survives_as_a_maintenance_candidate_signal(service, principal) -> None:
    """Duplicate content stays discoverable by digest for later maintenance."""

    first = service.write(principal, _request(source_id="a"))
    second = service.write(principal, _request(source_id="b"))

    left = service.get(principal, first.record_id)
    right = service.get(principal, second.record_id)

    assert left is not None and right is not None
    assert left.normalized_digest == right.normalized_digest
