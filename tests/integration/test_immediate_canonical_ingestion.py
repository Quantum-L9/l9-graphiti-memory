# L9_META
#   l9_schema: 1
#   repo: Quantum-L9/l9-graphiti-memory
#   path: tests/integration/test_immediate_canonical_ingestion.py
#   layer: test
#   owner: memory-control-plane
#   status: active
#   version: 2.3.0
#   updated: 2026-08-20

"""SP-02 / SP-03: canonical ingestion is immediate or it is a visible failure."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from l9_graphite_memory.admission.normalization import canonical_json, sha256_text
from l9_graphite_memory.errors import StoreError
from l9_graphite_memory.integrations import SessionEvent, SessionIngestor
from l9_graphite_memory.migration import LegacyWriteQueueDrain

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPO_ROOT / "src" / "l9_graphite_memory"


def test_store_failure_surfaces_as_failure_not_queued_success(
    memory_service,
    principal,
    monkeypatch,
) -> None:
    """SP-02: a canonical-store fault must reach the caller as a failure."""

    def fail_write(*_args, **_kwargs):
        raise StoreError("canonical store unavailable")

    monkeypatch.setattr(memory_service.store, "commit_write", fail_write)
    ingestor = SessionIngestor(memory_service)

    with pytest.raises(StoreError):
        ingestor.ingest(
            principal,
            SessionEvent(session_id="session-1", sequence=1, content="durable event"),
            namespace="repo-a",
        )


def test_session_ingestor_exposes_no_deferred_success_surface() -> None:
    """SP-03: there is no 'accepted but not yet canonical' return path."""

    assert not hasattr(SessionIngestor, "ingest_or_queue")
    assert not any(
        name.startswith("enqueue") or "queue" in name.casefold()
        for name in vars(SessionIngestor)
    )


def test_no_runtime_path_persists_a_write_request_for_later_ingestion() -> None:
    """SP-03: the structural guard proves no live enqueue path survives."""

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "tools" / "assurance" / "check_memory_write_bypass.py"),
            "--repo-root",
            str(REPO_ROOT),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["violations"] == []


def test_recovery_package_is_removed() -> None:
    """SP-03 / RG-01: the deferred-ingestion subsystem no longer exists."""

    assert not (SOURCE_ROOT / "recovery").exists()
    with pytest.raises(ImportError):
        __import__("l9_graphite_memory.recovery")


def test_legacy_drain_is_one_way_and_replays_through_the_service(
    tmp_path,
    memory_service,
    principal,
) -> None:
    """Legacy queued writes are drained through MemoryService, never re-queued."""

    queue_root = tmp_path / "write-recovery"
    pending = queue_root / "pending"
    pending.mkdir(parents=True)

    request = SessionIngestor.request(
        principal,
        SessionEvent(session_id="legacy-1", sequence=7, content="legacy event"),
        namespace="repo-a",
    )
    payload = request.model_dump(mode="json")
    queue_id = "3f2c1d5e-6a7b-4c8d-9e0f-1a2b3c4d5e6f"
    (pending / f"{queue_id}.json").write_text(
        json.dumps(
            {
                "queue_id": queue_id,
                "request": payload,
                "request_digest": sha256_text(canonical_json(payload)),
                "attempts": 1,
                "last_error": "StoreError: canonical store unavailable",
                "created_at": "2026-08-01T00:00:00+00:00",
                "updated_at": "2026-08-01T00:00:00+00:00",
            }
        ),
        encoding="utf-8",
    )

    drain = LegacyWriteQueueDrain(queue_root)
    assert not hasattr(drain, "enqueue")

    preview = drain.drain(memory_service, principal, apply=False)
    assert preview.attempted == 1
    assert preview.delivered == 0
    assert drain.pending_paths()

    report = drain.drain(memory_service, principal, apply=True)
    assert report.delivered == 1
    assert report.drained_cleanly
    assert drain.pending_paths() == ()

    record_id = report.items[0].receipt.record_id
    assert memory_service.get(principal, record_id) is not None


def test_legacy_drain_preserves_undeliverable_items(
    tmp_path,
    memory_service,
    principal,
) -> None:
    """No queued write is dropped silently when it cannot be admitted."""

    queue_root = tmp_path / "write-recovery"
    pending = queue_root / "pending"
    pending.mkdir(parents=True)
    (pending / "broken.json").write_text("{ not json", encoding="utf-8")

    report = LegacyWriteQueueDrain(queue_root).drain(memory_service, principal)

    assert report.unreadable == 1
    assert not report.drained_cleanly
    assert (pending / "broken.json").exists()
