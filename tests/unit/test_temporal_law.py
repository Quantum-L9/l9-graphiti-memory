# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_temporal_law.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-04

"""ADR-029: every temporal coordinate is timezone-aware UTC.

Finding F-08 (2026-09-04 audit): the contracts accepted naive datetimes, SQLite
compared the stored ISO text lexically (so a ``+02:00`` value filed against
UTC neighbours in the wrong order), and the in-memory store raised a
``TypeError`` that retrieval swallowed into a FAILED receipt.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from l9_graphite_memory.contracts import (
    ConsentGrant,
    EvidenceKind,
    EvidenceRef,
    HydrationRequest,
    MemorySearchRequest,
    MemoryWriteRequest,
    OperationStatus,
    Provenance,
    TemporalCoordinates,
)

PLUS_TWO = timezone(timedelta(hours=2))


def _naive(*parts: int) -> datetime:
    """A deliberately naive datetime: the value the boundary must refuse."""

    return datetime(*parts)  # noqa: DTZ001


def _write(content: str, **kwargs) -> MemoryWriteRequest:
    return MemoryWriteRequest(
        namespace="repo-a",
        content=content,
        provenance=Provenance(source="test"),
        evidence=(EvidenceRef(kind=EvidenceKind.EXPLICIT, description="t"),),
        **kwargs,
    )


def test_write_request_refuses_naive_coordinates() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        _write("x", valid_from=_naive(2026, 1, 1))
    with pytest.raises(ValidationError, match="timezone-aware"):
        _write("x", valid_to=_naive(2030, 1, 1))
    with pytest.raises(ValidationError, match="timezone-aware"):
        _write("x", source_observed_at=_naive(2026, 1, 1))


def test_search_and_hydration_requests_refuse_naive_coordinates() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        MemorySearchRequest(query="q", valid_at=_naive(2026, 1, 1))
    with pytest.raises(ValidationError, match="timezone-aware"):
        MemorySearchRequest(query="q", recorded_before=_naive(2026, 1, 1))
    with pytest.raises(ValidationError, match="timezone-aware"):
        HydrationRequest(task="t", valid_at=_naive(2026, 1, 1))


def test_aware_non_utc_input_is_normalized_to_utc() -> None:
    request = _write("x", valid_from=datetime(2026, 1, 1, 12, tzinfo=PLUS_TWO))
    assert request.valid_from.tzinfo == timezone.utc
    assert request.valid_from == datetime(2026, 1, 1, 10, tzinfo=timezone.utc)
    search = MemorySearchRequest(query="q", valid_at=datetime(2026, 1, 1, 12, tzinfo=PLUS_TWO))
    assert search.valid_at.utcoffset() == timedelta(0)


def test_persisted_coordinates_read_naive_values_as_utc() -> None:
    """Rows written before the boundary was enforced stay readable."""

    coordinates = TemporalCoordinates(
        valid_from=_naive(2026, 1, 1), recorded_at=_naive(2026, 1, 1, 0, 0, 1)
    )
    assert coordinates.valid_from == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert coordinates.recorded_at.tzinfo == timezone.utc
    consent = ConsentGrant(
        subject_id="s",
        namespace="repo-a",
        purpose="p",
        evidence=EvidenceRef(kind=EvidenceKind.EXPLICIT, description="e"),
        granted_at=_naive(2026, 1, 1),
    )
    assert consent.granted_at.tzinfo == timezone.utc


def test_offset_coordinates_filter_correctly_in_sqlite(sqlite_service, principal) -> None:
    """A +02:00 validity window is the same window as its UTC equivalent."""

    start = datetime(2026, 3, 1, 12, tzinfo=PLUS_TWO)  # 10:00Z
    end = datetime(2026, 3, 1, 14, tzinfo=PLUS_TWO)  # 12:00Z
    sqlite_service.write(principal, _write("offset window", valid_from=start, valid_to=end))

    def hits(at: datetime) -> int:
        return len(
            sqlite_service.search(
                principal,
                MemorySearchRequest(query="offset window", namespaces=("repo-a",), valid_at=at),
            ).hits
        )

    assert hits(datetime(2026, 3, 1, 11, tzinfo=timezone.utc)) == 1
    assert hits(datetime(2026, 3, 1, 9, 59, tzinfo=timezone.utc)) == 0
    # Lexical comparison of "12:00+02:00" against "13:00+00:00" would have
    # judged the window still open here; the normalized coordinates close it.
    assert hits(datetime(2026, 3, 1, 13, tzinfo=timezone.utc)) == 0


def test_search_with_offset_valid_at_is_a_complete_operation(memory_service, principal) -> None:
    memory_service.write(principal, _write("aware content"))
    receipt = memory_service.search(
        principal,
        MemorySearchRequest(
            query="aware content",
            namespaces=("repo-a",),
            valid_at=datetime.now(PLUS_TWO) + timedelta(minutes=1),
        ),
    )
    assert receipt.status is OperationStatus.COMPLETE
    assert len(receipt.hits) == 1
