# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/conformance/test_maintenance_ledger.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.2.0
#   updated: 2026-07-22

"""Maintenance run ledger and watermark behave identically on every backend."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from l9_graphite_memory.contracts import (
    AuthorizationAction,
    AuthorizationReceipt,
    MaintenanceAction,
    MaintenanceOperation,
    MaintenanceRunReceipt,
)
from tests.conftest import STORE_BACKENDS, make_store

NOW = datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)


def _authorization() -> AuthorizationReceipt:
    return AuthorizationReceipt(
        principal_id="nightly-maintenance",
        action=AuthorizationAction.MAINTAIN,
        namespace="repo-a",
        allowed=True,
        reasons=("namespace matched maintain grant",),
    )


def _action(digest: str, *, applied: bool = True) -> MaintenanceAction:
    return MaintenanceAction(
        operation=MaintenanceOperation.DEDUPE,
        reason="consolidated duplicate observations",
        action_digest=digest,
        applied=applied,
    )


def _run(
    *,
    watermark: datetime,
    applied: bool,
    actions: tuple[MaintenanceAction, ...] = (),
) -> MaintenanceRunReceipt:
    return MaintenanceRunReceipt(
        tenant_id="tenant-a",
        namespace="repo-a",
        applied=applied,
        watermark=watermark,
        actions=actions,
        authorization=_authorization(),
        actor="tenant-a:nightly-maintenance",
        reason="scheduled maintenance",
        started_at=watermark,
        completed_at=watermark,
    )


@pytest.fixture(params=STORE_BACKENDS)
def store(request, tmp_path):
    store = make_store(request.param, tmp_path)
    store.initialize()
    yield store
    store.close()


def test_watermark_is_absent_before_any_run(store) -> None:
    assert store.get_maintenance_watermark("tenant-a", "repo-a") is None
    assert store.find_maintenance_action_digests("tenant-a", "repo-a") == frozenset()


def test_applied_run_advances_the_watermark(store) -> None:
    store.save_maintenance_run(_run(watermark=NOW, applied=True))

    assert store.get_maintenance_watermark("tenant-a", "repo-a") == NOW


def test_dry_run_does_not_advance_the_watermark(store) -> None:
    """A planned-only run must not make the next run skip records."""

    store.save_maintenance_run(_run(watermark=NOW, applied=False))

    assert store.get_maintenance_watermark("tenant-a", "repo-a") is None


def test_watermark_takes_the_latest_applied_run(store) -> None:
    later = NOW + timedelta(days=1)
    store.save_maintenance_run(_run(watermark=NOW, applied=True))
    store.save_maintenance_run(_run(watermark=later, applied=True))

    assert store.get_maintenance_watermark("tenant-a", "repo-a") == later


def test_watermark_is_scoped_per_tenant_and_namespace(store) -> None:
    store.save_maintenance_run(_run(watermark=NOW, applied=True))

    assert store.get_maintenance_watermark("tenant-a", "repo-b") is None
    assert store.get_maintenance_watermark("tenant-b", "repo-a") is None


def test_applied_action_digests_are_recorded(store) -> None:
    digest = "a" * 64
    store.save_maintenance_run(_run(watermark=NOW, applied=True, actions=(_action(digest),)))

    assert store.find_maintenance_action_digests("tenant-a", "repo-a") == frozenset({digest})


def test_unapplied_action_digests_are_not_recorded(store) -> None:
    """A planned action must not suppress itself on the next real run."""

    digest = "b" * 64
    store.save_maintenance_run(
        _run(watermark=NOW, applied=False, actions=(_action(digest, applied=False),))
    )

    assert store.find_maintenance_action_digests("tenant-a", "repo-a") == frozenset()


def test_repeating_an_action_digest_across_runs_is_idempotent(store) -> None:
    digest = "c" * 64
    store.save_maintenance_run(_run(watermark=NOW, applied=True, actions=(_action(digest),)))
    store.save_maintenance_run(
        _run(
            watermark=NOW + timedelta(days=1),
            applied=True,
            actions=(_action(digest),),
        )
    )

    assert store.find_maintenance_action_digests("tenant-a", "repo-a") == frozenset({digest})
