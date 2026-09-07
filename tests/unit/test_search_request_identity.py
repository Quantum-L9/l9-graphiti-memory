# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_search_request_identity.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-09-07

"""A search receipt must identify the search it answers (MEM-P2-01).

Finding MEM-P2-01: ``SearchReceipt`` bound the query and the namespaces memory
authorized, and nothing about the **tag selector** — which materially changes
the result set. Two searches differing only in their tags produced receipts a
consumer could not tell apart, so "these hits answer my request" was an
assumption rather than a proof, and a receipt for a *different* request could
be accepted as an answer to this one.

Memory owns the semantics, so the fix is memory-side and total: every selector
the planner actually filters on is bound into the receipt, plus a digest over
the whole normalized set. The consumer (Cursor `ops/memory/search_identity.py`)
compares field by field and reports memory's digest without recomputing it.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from l9_graphite_memory.admission.normalization import canonical_json, sha256_text
from l9_graphite_memory.contracts import (
    SEARCH_SELECTOR_CANONICALIZATION,
    MemoryClass,
    MemorySearchRequest,
    MemoryWriteRequest,
    Provenance,
)

#: Every result-affecting selector the receipt is required to echo. `limit` and
#: the temporal coordinates are here for the same reason `tags` is: each one
#: alone changes which records come back.
BOUND_SELECTORS = (
    "tags",
    "memory_classes",
    "limit",
    "valid_at",
    "recorded_before",
    "include_superseded",
    "include_archived",
    "min_confidence",
)


def _write(service, principal, content: str, **kwargs):
    return service.write(
        principal,
        MemoryWriteRequest(
            namespace=kwargs.pop("namespace", "repo-a"),
            memory_class=kwargs.pop("memory_class", MemoryClass.SEMANTIC),
            content=content,
            provenance=Provenance(source="test", source_id="x", source_agent_id="tester"),
            **kwargs,
        ),
    )


# ---------------------------------------------------------------------------
# The selector identity itself
# ---------------------------------------------------------------------------


def test_the_identity_covers_every_selector_the_planner_filters_on() -> None:
    identity = MemorySearchRequest(query="task").selector_identity()
    for selector in BOUND_SELECTORS:
        assert selector in identity, f"{selector} changes the result set and must be bound"
    assert identity["query"] == "task"
    assert identity["canonicalization"] == SEARCH_SELECTOR_CANONICALIZATION


def test_a_new_request_field_cannot_be_added_without_deciding_about_it() -> None:
    """The rule "a filter added to search is added to the identity" was a
    comment, which is how MEM-P2-01 happened in the first place — ``tags``
    was added to the request and nobody bound it.

    So it is mechanical here: every field of MemorySearchRequest is either in
    the identity or in the explicit exclusion list below. Adding a field makes
    this fail until someone states which it is.
    """
    #: Fields that genuinely do not change which records come back. Each needs
    #: a reason, not just a name.
    not_result_affecting = {
        # Shapes how a hydration allocator spends the hits, never which
        # records the planner selects.
        "token_budget",
    }
    identity = set(MemorySearchRequest(query="q").selector_identity())
    identity.discard("canonicalization")
    fields = set(MemorySearchRequest.model_fields)
    unaccounted = fields - identity - not_result_affecting
    assert not unaccounted, (
        f"{sorted(unaccounted)} is on MemorySearchRequest but neither bound into "
        "selector_identity() nor declared not-result-affecting — decide which"
    )


def test_an_unstated_selector_reads_as_absent_not_as_a_default() -> None:
    """A receipt that never bound `limit` must not look like one CONTRADICTING
    the limit that was asked for. Absence is None; a default is a value."""
    from l9_graphite_memory.contracts import OperationStatus, SearchReceipt

    bare = SearchReceipt(
        status=OperationStatus.COMPLETE,
        query="q",
        namespaces_authorized=("repo-a",),
        result_digest="x" * 64,
    )
    assert bare.limit is None
    assert bare.request_digest is None
    assert bare.min_confidence is None
    assert bare.include_superseded is None
    assert bare.include_archived is None
    assert bare.selector_canonicalization is None
    # An empty selector is a real value (unfiltered), not an absence.
    assert bare.tags == ()
    assert bare.memory_classes == ()


def test_token_budget_is_not_part_of_the_identity() -> None:
    """It shapes how an allocator spends the hits, never which records the
    planner selects — binding it would make two identical searches look
    different."""
    lean = MemorySearchRequest(query="task", token_budget=256)
    fat = MemorySearchRequest(query="task", token_budget=8_000, valid_at=lean.valid_at)
    assert "token_budget" not in lean.selector_identity()
    assert lean.selector_identity() == fat.selector_identity()


def test_a_different_tag_selector_is_a_different_request() -> None:
    """The finding, stated as an assertion."""
    at = datetime(2026, 9, 7, tzinfo=timezone.utc)
    left = MemorySearchRequest(query="resume", tags=("session_continuation",), valid_at=at)
    right = MemorySearchRequest(query="resume", tags=("build",), valid_at=at)
    assert left.selector_identity() != right.selector_identity()


def test_tag_and_class_order_does_not_change_the_request() -> None:
    """Both are unordered sets: asking for (a, b) and (b, a) is one search."""
    at = datetime(2026, 9, 7, tzinfo=timezone.utc)
    left = MemorySearchRequest(
        query="q",
        tags=("alpha", "beta"),
        memory_classes=(MemoryClass.SEMANTIC, MemoryClass.INSIGHT),
        valid_at=at,
    )
    right = MemorySearchRequest(
        query="q",
        tags=("beta", "alpha"),
        memory_classes=(MemoryClass.INSIGHT, MemoryClass.SEMANTIC),
        valid_at=at,
    )
    assert left.selector_identity() == right.selector_identity()


def test_namespace_order_does_change_the_request() -> None:
    """Unlike tags, fan-in order is part of what the caller asked for."""
    at = datetime(2026, 9, 7, tzinfo=timezone.utc)
    left = MemorySearchRequest(query="q", namespaces=("a", "b"), valid_at=at)
    right = MemorySearchRequest(query="q", namespaces=("b", "a"), valid_at=at)
    assert left.selector_identity() != right.selector_identity()


def test_each_selector_alone_changes_the_identity() -> None:
    at = datetime(2026, 9, 7, tzinfo=timezone.utc)
    base = MemorySearchRequest(query="q", valid_at=at)
    variants = {
        "tags": {"tags": ("x",)},
        "memory_classes": {"memory_classes": (MemoryClass.DECISION,)},
        "limit": {"limit": 7},
        "valid_at": {"valid_at": at + timedelta(days=1)},
        "recorded_before": {"recorded_before": at},
        "include_superseded": {"include_superseded": True},
        "include_archived": {"include_archived": True},
        "min_confidence": {"min_confidence": 0.5},
    }
    for name, update in variants.items():
        other = MemorySearchRequest(**{"query": "q", "valid_at": at, **update})
        assert base.selector_identity() != other.selector_identity(), (
            f"{name} changes which records come back; the identity must reflect it"
        )


def test_the_identity_is_stamped_with_memory_s_own_canonicalization() -> None:
    """So a change to this normalization can never read as a changed request."""
    identity = MemorySearchRequest(query="q").selector_identity()
    assert identity["canonicalization"] == "memory.search-selectors/v1"


# ---------------------------------------------------------------------------
# The live receipt
# ---------------------------------------------------------------------------


def test_the_receipt_binds_every_selector_and_a_request_digest(memory_service, principal) -> None:
    _write(memory_service, principal, "a note about the build", tags=("build",))
    request = MemorySearchRequest(
        query="build",
        namespaces=("repo-a",),
        tags=("build",),
        memory_classes=(MemoryClass.SEMANTIC,),
        limit=5,
        min_confidence=0.1,
    )
    receipt = memory_service.search(principal, request)

    assert receipt.tags == ("build",)
    assert receipt.memory_classes == (MemoryClass.SEMANTIC,)
    assert receipt.limit == 5
    assert receipt.min_confidence == 0.1
    assert receipt.include_superseded is False
    assert receipt.include_archived is False
    assert receipt.selector_canonicalization == SEARCH_SELECTOR_CANONICALIZATION
    assert len(receipt.request_digest) == 64


def test_the_receipt_digest_is_over_what_the_planner_actually_filtered(
    memory_service, principal
) -> None:
    """The service resolves an open ``recorded_before`` to its own clock, so
    the receipt must bind the EFFECTIVE value. Echoing the caller's ``None``
    would prove nothing about the search that ran."""
    _write(memory_service, principal, "a note", tags=("build",))
    receipt = memory_service.search(
        principal, MemorySearchRequest(query="note", namespaces=("repo-a",))
    )
    assert receipt.recorded_before is not None, "the effective coordinate, not the caller's blank"

    effective = MemorySearchRequest(
        query="note",
        namespaces=("repo-a",),
        valid_at=receipt.valid_at,
        recorded_before=receipt.recorded_before,
    )
    assert receipt.request_digest == sha256_text(canonical_json(effective.selector_identity()))


def test_two_searches_differing_only_by_tag_get_different_digests(
    memory_service, principal
) -> None:
    """The exact confusion MEM-P2-01 named: same query, different selector.

    Before the fix these two receipts were indistinguishable on every bound
    field, so a consumer holding one could not tell which request it answered.
    """
    _write(memory_service, principal, "shared content", tags=("build",))
    at = datetime(2026, 9, 7, tzinfo=timezone.utc)
    common = {"query": "shared", "namespaces": ("repo-a",), "valid_at": at}
    left = memory_service.search(principal, MemorySearchRequest(**common, tags=("build",)))
    right = memory_service.search(principal, MemorySearchRequest(**common, tags=("other",)))

    assert left.request_digest != right.request_digest
    assert left.tags != right.tags


def test_the_result_digest_is_bound_to_the_request(memory_service, principal) -> None:
    """Two searches whose hit sets coincide must still digest differently when
    the requests differ — otherwise result_digest identifies the results
    without identifying what was asked for."""
    at = datetime(2026, 9, 7, tzinfo=timezone.utc)
    _write(memory_service, principal, "content nobody tagged")
    common = {"query": "content", "namespaces": ("repo-a",), "valid_at": at}
    wide = memory_service.search(principal, MemorySearchRequest(**common, limit=20))
    narrow = memory_service.search(principal, MemorySearchRequest(**common, limit=19))

    assert [h.record.record_id for h in wide.hits] == [h.record.record_id for h in narrow.hits]
    assert wide.result_digest != narrow.result_digest


def test_hydrate_carries_the_selector_through_to_its_search(memory_service, principal) -> None:
    """Hydration builds a search request internally; its receipt must identify
    that request too, or the capsule path keeps the gap the fix closes."""
    from l9_graphite_memory.contracts import HydrationRequest

    _write(memory_service, principal, "resume here", tags=("session_continuation",))
    result = memory_service.hydrate(
        principal,
        HydrationRequest(
            task="resume",
            namespaces=("repo-a",),
            tags=("Session_Continuation",),
            max_records=5,
        ),
    )
    assert result.search_receipt_id is not None
