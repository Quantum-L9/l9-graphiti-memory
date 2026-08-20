# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/unit/test_maintenance_authority.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""SP-10 / SP-11: least-privilege MAINTAIN, and a contract that cannot ingest."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from l9_graphite_memory.authz import NamespacePolicy
from l9_graphite_memory.contracts import (
    AuthorizationAction,
    MaintenanceOperation,
    MaintenanceRequest,
    MemoryPrincipal,
)
from l9_graphite_memory.errors import AuthorizationError

# Field names that would turn maintenance into an ingestion surface. None of
# these may be accepted by MaintenanceRequest, now or after future edits.
INGESTION_SHAPED_FIELDS = (
    "content",
    "transcript",
    "messages",
    "document",
    "source_text",
    "raw",
    "raw_source",
    "episode",
    "text",
    "body",
    "payload",
    "records",
    "memory_class",
    "provenance",
    "evidence",
)

# The complete field set the contract is allowed to declare.
ALLOWED_FIELDS = {
    "namespace",
    "operations",
    "watermark",
    "max_records",
    "max_actions",
    "dry_run",
    "reason",
}


@pytest.fixture
def maintainer() -> MemoryPrincipal:
    """The nightly principal: MAINTAIN and READ only. No admin, no write."""

    return MemoryPrincipal(
        principal_id="nightly-maintenance",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        maintain_namespaces=("repo-a",),
    )


def test_maintain_is_granted_without_administrator_authority(maintainer) -> None:
    """SP-10: MAINTAIN works on its own grant, not by being an administrator."""

    policy = NamespacePolicy()

    assert maintainer.is_admin is False
    receipt = policy.require(maintainer, AuthorizationAction.MAINTAIN, "repo-a")
    assert receipt.allowed is True


def test_maintain_does_not_confer_write_delete_or_admin(maintainer) -> None:
    """SP-10: the nightly grant cannot ingest, promote, or administer."""

    policy = NamespacePolicy()

    for action in (
        AuthorizationAction.WRITE,
        AuthorizationAction.PROMOTE,
        AuthorizationAction.ARCHIVE,
        AuthorizationAction.ADMIN,
    ):
        assert policy.evaluate(maintainer, action, "repo-a").allowed is False
        with pytest.raises(AuthorizationError):
            policy.require(maintainer, action, "repo-a")


def test_maintain_is_scoped_to_granted_namespaces(maintainer) -> None:
    policy = NamespacePolicy()

    assert (
        policy.evaluate(maintainer, AuthorizationAction.MAINTAIN, "repo-b").allowed
        is False
    )


def test_write_grant_does_not_confer_maintain() -> None:
    """The two authorities are independent in both directions."""

    writer = MemoryPrincipal(
        principal_id="agent",
        tenant_id="tenant-a",
        read_namespaces=("repo-a",),
        write_namespaces=("repo-a",),
    )
    policy = NamespacePolicy()

    assert policy.evaluate(writer, AuthorizationAction.WRITE, "repo-a").allowed is True
    assert (
        policy.evaluate(writer, AuthorizationAction.MAINTAIN, "repo-a").allowed is False
    )


@pytest.mark.parametrize("field", INGESTION_SHAPED_FIELDS)
def test_maintenance_request_rejects_ingestion_payloads(field: str) -> None:
    """SP-11: the contract cannot carry a transcript or any other raw source."""

    with pytest.raises(ValidationError):
        MaintenanceRequest(**{"namespace": "repo-a", field: "raw source material"})


def test_maintenance_request_declares_no_ingestion_capable_field() -> None:
    """SP-11 structurally: adding an ingestion field later fails this test."""

    declared = set(MaintenanceRequest.model_fields)

    assert declared == ALLOWED_FIELDS
    assert declared.isdisjoint(INGESTION_SHAPED_FIELDS)


def test_maintenance_request_defaults_are_bounded() -> None:
    request = MaintenanceRequest(namespace="repo-a")

    assert request.operations == tuple(MaintenanceOperation)
    assert request.max_records <= 100_000
    assert request.max_actions <= 10_000
    assert request.watermark is None
    assert request.dry_run is False


def test_maintenance_request_requires_unique_non_empty_operations() -> None:
    with pytest.raises(ValidationError, match="at least one operation"):
        MaintenanceRequest(namespace="repo-a", operations=())

    with pytest.raises(ValidationError, match="must be unique"):
        MaintenanceRequest(
            namespace="repo-a",
            operations=(MaintenanceOperation.DEDUPE, MaintenanceOperation.DEDUPE),
        )


def test_maintenance_request_is_immutable() -> None:
    request = MaintenanceRequest(namespace="repo-a")

    with pytest.raises(ValidationError):
        request.namespace = "repo-b"


def test_watermark_is_accepted_as_an_explicit_upper_bound() -> None:
    watermark = datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)
    request = MaintenanceRequest(namespace="repo-a", watermark=watermark)

    assert request.watermark == watermark
